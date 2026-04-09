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
    181: 'program_fail_count',
    182: 'erase_fail_count',
    187: 'reported_uncorrectable_errors',
    188: 'command_timeout',
    190: 'airflow_temperature',
    192: 'power_off_retract_count',
    193: 'load_cycle_count',
    194: 'temperature',
    196: 'reallocated_event_count',
    197: 'current_pending_sectors',
    198: 'offline_uncorrectable',
    199: 'udma_crc_error_count',
    235: 'por_recovery_count',
    240: 'head_flying_hours',
    241: 'total_lbas_written',
    242: 'total_lbas_read',
}

# Attributes where non-zero raw values indicate potential problems.
# Per Backblaze's large-scale drive failure analysis, these four are the
# strongest predictors of imminent failure:
#   5   - reallocated_sectors
#   187 - reported_uncorrectable_errors
#   197 - current_pending_sectors
#   198 - offline_uncorrectable
WARNING_ATTRIBUTES = {5, 187, 197, 198}

# Attributes whose raw value is a monotonic counter (only ever increases).
# These are emitted via self.monotonic_count() so Datadog stores the
# per-interval delta, which enables trivial rate queries and alerting
# on "errors increased in the last N minutes". Attributes not listed
# here (temperature, current_pending_sectors, offline_uncorrectable,
# raw_read_error_rate, spin_up_time, airflow_temperature) are emitted as
# gauges because they can fluctuate or decrease in the drive's lifetime.
MONOTONIC_ATTRIBUTES = {
    4,    # start_stop_count
    5,    # reallocated_sectors
    9,    # power_on_hours
    10,   # spin_retry_count
    12,   # power_cycle_count
    177,  # wear_leveling_count
    179,  # used_reserved_block_count
    181,  # program_fail_count
    182,  # erase_fail_count
    187,  # reported_uncorrectable_errors
    188,  # command_timeout
    192,  # power_off_retract_count
    193,  # load_cycle_count
    196,  # reallocated_event_count
    199,  # udma_crc_error_count
    235,  # por_recovery_count
    240,  # head_flying_hours
    241,  # total_lbas_written
    242,  # total_lbas_read
}

# Top-level state file fields smartd writes outside the attribute section.
# smartd only writes some of these when they're non-zero, so absent ones are
# reported as 0 to keep time series continuous.
#
# Split by metric type: error/event counters are monotonic, while
# self-test-last-err-hour is a pointer-like gauge that jumps to a new
# power-on-hour value rather than accumulating.
#
# scheduled-test-next-check is deliberately omitted: smartd writes it as
# a Unix timestamp of the next scheduled self-test, which is not useful
# as a gauge time series in Datadog.
TOP_LEVEL_MONOTONIC_METRICS = {
    'ata-error-count': 'ata_error_count',
    'self-test-errors': 'self_test_errors',
}
TOP_LEVEL_GAUGE_METRICS = {
    # Power-on hour at which the last self-test error occurred. Not a wall
    # clock timestamp — it's in the same units as power_on_hours, so users
    # can derive "hours since last self-test error".
    'self-test-last-err-hour': 'self_test_last_err_hour',
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
        # Cached once so per-check() hot path doesn't re-read and re-copy
        # the instance tags on every invocation.
        self.custom_tags = list(self.instance.get('tags') or [])

    def check(self, _):
        """Discover smartd state files and emit metrics + service checks.

        Top-level errors (missing state dir, no files matched) are reported
        via the `can_read` service check. Per-drive parse/emit logic lives
        in `_process_state_file`.
        """
        pattern = os.path.join(self.state_dir, self.file_pattern)

        if not os.path.isdir(self.state_dir):
            message = (
                'smartd state directory {} does not exist. smartd must be '
                'launched with the "-s <prefix>" argument to persist per-drive '
                'state files. See the README Prerequisites section.'
            ).format(self.state_dir)
            self.service_check(
                'can_read', AgentCheck.CRITICAL, tags=self.custom_tags, message=message
            )
            self.log.error(message)
            return

        state_files = sorted(glob.glob(pattern))
        if not state_files:
            message = (
                'No smartd state files found matching {}. smartd must be '
                'launched with the "-s <prefix>" argument to persist per-drive '
                'state files. See the README Prerequisites section.'
            ).format(pattern)
            self.service_check(
                'can_read', AgentCheck.CRITICAL, tags=self.custom_tags, message=message
            )
            self.log.error(message)
            return

        for path in state_files:
            self._process_state_file(path)

        self.service_check('can_read', AgentCheck.OK, tags=self.custom_tags)

    def _process_state_file(self, path):
        """Parse a single smartd state file and emit its metrics + disk_health
        service check. Returns silently if the filename isn't parseable;
        parse errors downgrade the drive's health to CRITICAL with a tagged
        message rather than killing the whole check."""
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

        tags = device_tags + self.custom_tags

        try:
            attributes, top_level = self._parse_state_file(path)
        except Exception as e:
            message = 'Failed to parse state file {}: {}'.format(filename, e)
            self.log.error(message)
            self.service_check('disk_health', AgentCheck.CRITICAL, tags=tags, message=message)
            return

        # Emit top-level metrics. smartd only writes these fields when they're
        # non-zero, so default absent ones to 0 for clean time series.
        for key, metric_name in TOP_LEVEL_MONOTONIC_METRICS.items():
            self.monotonic_count(metric_name, top_level.get(key, 0), tags=tags)
        for key, metric_name in TOP_LEVEL_GAUGE_METRICS.items():
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

        # Note: monotonic_count drops the first sample per (metric, tag-set)
        # after an agent restart — it establishes a baseline and emits deltas
        # from there on. This is the desired behavior for counters; it just
        # means "errors in the last N minutes" queries have a one-interval
        # warm-up after a restart.
        critical_messages = []
        warning_messages = []

        for attr_id, attr_data in recognized.items():
            metric_name = NAMED_ATTRIBUTES[attr_id]

            raw = attr_data.get('raw', 0)
            val = attr_data.get('val')

            if metric_name == 'temperature':
                # Temperature is encoded in the lowest byte of the raw value
                value = raw & 0xFF
            else:
                value = raw

            if attr_id in MONOTONIC_ATTRIBUTES:
                self.monotonic_count(metric_name, value, tags=tags)
            else:
                self.gauge(metric_name, value, tags=tags)

            # Health checks. `val is not None` guards the case where smartd
            # wrote a raw= line but no val= line yet (shouldn't happen in
            # practice, but we don't want a missing normalized value to
            # masquerade as a failing drive).
            if val is not None and val == 0:
                critical_messages.append(
                    'Attribute {} ({}) normalized value is 0'.format(attr_id, metric_name)
                )
            elif attr_id in WARNING_ATTRIBUTES and raw > 0:
                warning_messages.append(
                    'Attribute {} ({}): raw value {}'.format(attr_id, metric_name, raw)
                )

        if critical_messages:
            health = AgentCheck.CRITICAL
            health_message = '; '.join(critical_messages)
        elif warning_messages:
            health = AgentCheck.WARNING
            health_message = '; '.join(warning_messages)
        else:
            health = AgentCheck.OK
            health_message = None

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
            matches.sort()
            self.log.warning(
                'Multiple by-id symlinks match %s, using first sorted: %s',
                pattern, matches,
            )
        try:
            target = os.readlink(matches[0])
        except OSError as e:
            self.log.debug('Failed to readlink %s: %s', matches[0], e)
            return None
        return os.path.basename(target)

    def _parse_state_file(self, path):
        """Parse a smartd state file into (attributes, top_level).

        `attributes` is re-keyed by SMART attribute ID (e.g. 194) rather
        than the file's arbitrary `ata-smart-attribute.<idx>` index.
        `top_level` holds bare `key = value` lines like `ata-error-count`.
        """
        attributes = {}
        top_level = {}

        with open(path, encoding='utf-8') as f:
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
