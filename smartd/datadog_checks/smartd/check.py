import glob
import os
import re

from datadog_checks.base import AgentCheck

FILENAME_PATTERN = re.compile(r'^smartd\.(.+)-([^-]+)\.\w+\.state$')

# SMART attribute ID → metric name mapping
NAMED_ATTRIBUTES = {
    1: 'raw_read_error_rate',
    3: 'spin_up_time',
    4: 'start_stop_count',
    5: 'reallocated_sectors',
    9: 'power_on_hours',
    10: 'spin_retry_count',
    12: 'power_cycle_count',
    177: 'wear_leveling_count',
    179: 'used_reserved_block_count',
    187: 'reported_uncorrectable_errors',
    190: 'airflow_temperature',
    192: 'power_off_retract_count',
    193: 'load_cycle_count',
    194: 'temperature',
    196: 'reallocated_event_count',
    197: 'current_pending_sectors',
    198: 'offline_uncorrectable',
    199: 'udma_crc_error_count',
    240: 'head_flying_hours',
    241: 'total_lbas_written',
    242: 'total_lbas_read',
}

# Attributes where non-zero raw values indicate potential problems
WARNING_ATTRIBUTES = {5, 187, 197, 198}

# Top-level state file fields smartd writes outside the attribute section.
# smartd only writes some of these when they're non-zero, so absent ones are
# reported as 0 to keep time series continuous.
TOP_LEVEL_METRICS = {
    'ata-error-count': 'ata_error_count',
    'self-test-errors': 'self_test_errors',
    'self-test-last-err-hour': 'self_test_last_err_hour',
    'scheduled-test-next-check': 'scheduled_test_next_check',
}

ATTR_LINE_PATTERN = re.compile(
    r'^ata-smart-attribute\.(\d+)\.(id|val|worst|raw)\s*=\s*(\d+)$'
)

# Matches top-level key=value lines like `ata-error-count = 873`. Deliberately
# does not match dotted keys (ata-smart-attribute.*, mail.*, etc.).
TOP_LEVEL_LINE_PATTERN = re.compile(r'^([a-z][a-z0-9-]*)\s*=\s*(\d+)$')


class SmartdCheck(AgentCheck):

    __NAMESPACE__ = 'smartd'

    def __init__(self, name, init_config, instances):
        super().__init__(name, init_config, instances)
        self.state_dir = self.instance.get('smartd_state_dir', '/var/lib/smartmontools')
        self.file_pattern = self.instance.get('file_pattern', 'smartd.*.state')
        self.dev_disk_by_id = self.instance.get('dev_disk_by_id', '/dev/disk/by-id')

    def check(self, _):
        pattern = os.path.join(self.state_dir, self.file_pattern)

        if not os.path.isdir(self.state_dir):
            message = (
                'smartd state directory {} does not exist. smartd must be '
                'launched with the "-s <prefix>" argument to persist per-drive '
                'state files. See the README Prerequisites section.'
            ).format(self.state_dir)
            self.service_check('can_read', AgentCheck.CRITICAL, message=message)
            self.log.error(message)
            return

        state_files = sorted(glob.glob(pattern))
        if not state_files:
            message = (
                'No smartd state files found matching {}. smartd must be '
                'launched with the "-s <prefix>" argument to persist per-drive '
                'state files. See the README Prerequisites section.'
            ).format(pattern)
            self.service_check('can_read', AgentCheck.CRITICAL, message=message)
            self.log.error(message)
            return

        for path in state_files:
            self._process_state_file(path)

        self.service_check('can_read', AgentCheck.OK)

    def _process_state_file(self, path):
        filename = os.path.basename(path)
        match = FILENAME_PATTERN.match(filename)
        if not match:
            self.log.warning('Could not parse device info from filename: %s', filename)
            return

        model = match.group(1)
        serial = match.group(2)
        device_tags = ['device_model:{}'.format(model), 'serial_number:{}'.format(serial)]

        device_name = self._resolve_device_name(serial)
        if device_name:
            device_tags.append('device:/dev/{}'.format(device_name))
            device_tags.append('device_name:{}'.format(device_name))

        tags = device_tags + self.instance.get('tags', [])

        try:
            attributes, top_level = self._parse_state_file(path)
        except Exception as e:
            self.log.error('Failed to parse state file %s: %s', path, e)
            self.service_check('disk_health', AgentCheck.CRITICAL, tags=tags, message=str(e))
            return

        # Emit top-level metrics. smartd only writes these fields when they're
        # non-zero, so default absent ones to 0 for clean time series.
        for key, metric_name in TOP_LEVEL_METRICS.items():
            self.gauge(metric_name, top_level.get(key, 0), tags=tags)

        recognized = {aid: data for aid, data in attributes.items() if aid in NAMED_ATTRIBUTES}
        if not recognized:
            # State file exists but has no SMART attribute data yet. This
            # commonly happens right after smartd starts and hasn't polled the
            # drive for the first time. Report UNKNOWN instead of silently OK.
            message = (
                'State file {} contains no recognized SMART attributes yet. '
                'This is normal shortly after smartd starts; the check will '
                'begin reporting once smartd writes attribute data on its '
                'next poll cycle.'
            ).format(os.path.basename(path))
            self.log.info(message)
            self.service_check('disk_health', AgentCheck.UNKNOWN, tags=tags, message=message)
            return

        health = AgentCheck.OK
        health_message = None

        for attr_id, attr_data in recognized.items():
            metric_name = NAMED_ATTRIBUTES[attr_id]

            raw = attr_data.get('raw', 0)
            val = attr_data.get('val', 0)

            if metric_name == 'temperature':
                # Temperature is encoded in the lowest byte of the raw value
                value = raw & 0xFF
            else:
                value = raw

            self.gauge(metric_name, value, tags=tags)

            # Health checks
            if val == 0:
                health = AgentCheck.CRITICAL
                health_message = 'Attribute {} normalized value is 0'.format(attr_id)
            elif attr_id in WARNING_ATTRIBUTES and raw > 0 and health != AgentCheck.CRITICAL:
                health = AgentCheck.WARNING
                health_message = 'Attribute {} ({}): raw value {}'.format(
                    attr_id, metric_name, raw
                )

        self.service_check('disk_health', health, tags=tags, message=health_message)

    def _resolve_device_name(self, serial):
        """Resolve the kernel device name (e.g. 'sdb') for a drive with the
        given serial number by globbing /dev/disk/by-id for an
        `ata-<model>_<serial>` symlink.

        We match on serial suffix because smartd normalizes dashes in the
        hardware model name to underscores when constructing state file
        names, while /dev/disk/by-id preserves the original dashes. Matching
        by serial sidesteps the ambiguity entirely and also skips partition
        symlinks (which have a `-partN` suffix).
        """
        pattern = os.path.join(
            self.dev_disk_by_id,
            'ata-*_' + glob.escape(serial),
        )
        matches = glob.glob(pattern)
        if not matches:
            self.log.debug('No by-id symlink matching %s', pattern)
            return None
        if len(matches) > 1:
            self.log.warning(
                'Multiple by-id symlinks match %s, using first sorted: %s',
                pattern, matches,
            )
            matches.sort()
        try:
            target = os.readlink(matches[0])
        except OSError as e:
            self.log.debug('Failed to readlink %s: %s', matches[0], e)
            return None
        return os.path.basename(target)

    def _parse_state_file(self, path):
        attributes = {}
        top_level = {}

        with open(path) as f:
            for line in f:
                line = line.strip()

                attr_match = ATTR_LINE_PATTERN.match(line)
                if attr_match:
                    idx = int(attr_match.group(1))
                    field = attr_match.group(2)
                    value = int(attr_match.group(3))
                    attributes.setdefault(idx, {})[field] = value
                    continue

                top_match = TOP_LEVEL_LINE_PATTERN.match(line)
                if top_match:
                    top_level[top_match.group(1)] = int(top_match.group(2))

        # Re-key attributes by SMART ID instead of file index
        result = {}
        for attr_data in attributes.values():
            attr_id = attr_data.get('id')
            if attr_id is not None:
                result[attr_id] = attr_data

        return result, top_level
