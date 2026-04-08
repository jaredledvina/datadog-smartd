import glob
import os
import re

from datadog_checks.base import AgentCheck

FILENAME_PATTERN = re.compile(r'^smartd\.(.+)-([^-]+)\.\w+\.state$')

# SMART attribute ID → metric name mapping
NAMED_ATTRIBUTES = {
    1: 'raw_read_error_rate',
    5: 'reallocated_sectors',
    9: 'power_on_hours',
    10: 'spin_retry_count',
    12: 'power_cycle_count',
    194: 'temperature',
    196: 'reallocated_event_count',
    197: 'current_pending_sectors',
    198: 'offline_uncorrectable',
    199: 'udma_crc_error_count',
}

# Attributes where non-zero raw values indicate potential problems
WARNING_ATTRIBUTES = {5, 197, 198}

ATTR_LINE_PATTERN = re.compile(
    r'^ata-smart-attribute\.(\d+)\.(id|val|worst|raw)\s*=\s*(\d+)$'
)


class SmartdCheck(AgentCheck):

    __NAMESPACE__ = 'smartd'

    def __init__(self, name, init_config, instances):
        super().__init__(name, init_config, instances)
        self.state_dir = self.instance.get('smartd_state_dir', '/var/lib/smartmontools')
        self.file_pattern = self.instance.get('file_pattern', 'smartd.*.state')
        self.dev_disk_by_id = self.instance.get('dev_disk_by_id', '/dev/disk/by-id')

    def check(self, _):
        pattern = os.path.join(self.state_dir, self.file_pattern)
        state_files = sorted(glob.glob(pattern))

        if not state_files:
            self.service_check('can_read', AgentCheck.CRITICAL, message='No smartd state files found')
            self.log.error('No smartd state files found matching %s', pattern)
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

        device_name = self._resolve_device_name(model, serial)
        if device_name:
            device_tags.append('device:/dev/{}'.format(device_name))
            device_tags.append('device_name:{}'.format(device_name))

        tags = device_tags + self.instance.get('tags', [])

        try:
            attributes = self._parse_state_file(path)
        except Exception as e:
            self.log.error('Failed to parse state file %s: %s', path, e)
            self.service_check('disk_health', AgentCheck.CRITICAL, tags=tags, message=str(e))
            return

        health = AgentCheck.OK
        health_message = None

        for attr_id, attr_data in attributes.items():
            metric_name = NAMED_ATTRIBUTES.get(attr_id)
            if metric_name is None:
                continue

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

    def _resolve_device_name(self, model, serial):
        """Resolve the kernel device name (e.g. 'sdb') for a drive with the
        given model and serial by reading the matching symlink under
        /dev/disk/by-id. Returns None if no matching symlink exists.
        """
        link = os.path.join(self.dev_disk_by_id, 'ata-{}_{}'.format(model, serial))
        try:
            target = os.readlink(link)
        except OSError:
            self.log.debug('No by-id symlink for %s_%s at %s', model, serial, link)
            return None
        return os.path.basename(target)

    def _parse_state_file(self, path):
        attributes = {}

        with open(path) as f:
            for line in f:
                line = line.strip()
                match = ATTR_LINE_PATTERN.match(line)
                if not match:
                    continue

                idx = int(match.group(1))
                field = match.group(2)
                value = int(match.group(3))

                if field == 'id':
                    attributes.setdefault(idx, {})['id'] = value
                elif field == 'val':
                    attributes.setdefault(idx, {})['val'] = value
                elif field == 'worst':
                    attributes.setdefault(idx, {})['worst'] = value
                elif field == 'raw':
                    attributes.setdefault(idx, {})['raw'] = value

        # Re-key by attribute ID instead of index
        result = {}
        for attr_data in attributes.values():
            attr_id = attr_data.get('id')
            if attr_id is not None:
                result[attr_id] = attr_data

        return result
