import os

import pytest

from datadog_checks.base import AgentCheck
from datadog_checks.base.stubs.aggregator import AggregatorStub
from datadog_checks.smartd import SmartdCheck

from .common import (
    CHECK_NAME,
    DEGRADED_TAGS,
    HEALTHY_TAGS,
    INSTANCE,
)

pytestmark = pytest.mark.unit

# Metric names that are emitted as monotonic counters. Kept in sync with
# MONOTONIC_ATTRIBUTES + TOP_LEVEL_MONOTONIC_METRICS in check.py.
MONOTONIC_METRICS = {
    'smartd.start_stop_count',
    'smartd.reallocated_sectors',
    'smartd.power_on_hours',
    'smartd.spin_retry_count',
    'smartd.power_cycle_count',
    'smartd.wear_leveling_count',
    'smartd.used_reserved_block_count',
    'smartd.program_fail_count',
    'smartd.erase_fail_count',
    'smartd.reported_uncorrectable_errors',
    'smartd.command_timeout',
    'smartd.power_off_retract_count',
    'smartd.load_cycle_count',
    'smartd.reallocated_event_count',
    'smartd.udma_crc_error_count',
    'smartd.por_recovery_count',
    'smartd.head_flying_hours',
    'smartd.total_lbas_written',
    'smartd.total_lbas_read',
    'smartd.ata_error_count',
    'smartd.self_test_errors',
}


def assert_smartd_metric(aggregator, name, value, tags):
    """Assert a smartd metric with the correct metric type."""
    metric_type = (
        AggregatorStub.MONOTONIC_COUNT if name in MONOTONIC_METRICS
        else AggregatorStub.GAUGE
    )
    aggregator.assert_metric(name, value=value, tags=tags, metric_type=metric_type)


def test_check_healthy_and_degraded(aggregator, dd_run_check):
    check = SmartdCheck(CHECK_NAME, {}, [INSTANCE])
    dd_run_check(check)

    # Healthy drive attribute metrics
    assert_smartd_metric(aggregator, 'smartd.raw_read_error_rate', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.spin_up_time', 38683869672, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.start_stop_count', 29, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.reallocated_sectors', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.power_on_hours', 91000, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.spin_retry_count', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.power_cycle_count', 29, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.power_off_retract_count', 1168, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.load_cycle_count', 1168, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.reallocated_event_count', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.current_pending_sectors', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.offline_uncorrectable', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.udma_crc_error_count', 0, HEALTHY_TAGS)
    # Healthy drive top-level metrics (all default to 0)
    assert_smartd_metric(aggregator, 'smartd.ata_error_count', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.self_test_errors', 0, HEALTHY_TAGS)
    assert_smartd_metric(aggregator, 'smartd.self_test_last_err_hour', 0, HEALTHY_TAGS)

    # Degraded drive attribute metrics
    assert_smartd_metric(aggregator, 'smartd.raw_read_error_rate', 12, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.spin_up_time', 42949672960, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.start_stop_count', 45, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.reallocated_sectors', 16, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.power_on_hours', 105000, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.spin_retry_count', 0, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.power_cycle_count', 45, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.power_off_retract_count', 2000, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.load_cycle_count', 2000, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.temperature', 41, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.reallocated_event_count', 16, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.current_pending_sectors', 2, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.offline_uncorrectable', 0, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.udma_crc_error_count', 3, DEGRADED_TAGS)
    # Degraded drive top-level metrics (three populated from fixture)
    assert_smartd_metric(aggregator, 'smartd.ata_error_count', 42, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.self_test_errors', 1, DEGRADED_TAGS)
    assert_smartd_metric(aggregator, 'smartd.self_test_last_err_hour', 98765, DEGRADED_TAGS)

    # Both drives emit a state file freshness gauge. Age is wall-clock
    # dependent so we only assert presence and type, not the exact value.
    aggregator.assert_metric(
        'smartd.state_file_age_seconds', tags=HEALTHY_TAGS, metric_type=AggregatorStub.GAUGE
    )
    aggregator.assert_metric(
        'smartd.state_file_age_seconds', tags=DEGRADED_TAGS, metric_type=AggregatorStub.GAUGE
    )

    # Service checks
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.OK, tags=HEALTHY_TAGS)
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.WARNING, tags=DEGRADED_TAGS)
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)

    aggregator.assert_all_metrics_covered()


def test_check_no_files(aggregator, dd_run_check):
    instance = {
        'smartd_state_dir': '/nonexistent/path',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    aggregator.assert_service_check('smartd.can_read', AgentCheck.CRITICAL)


def test_check_empty_file(aggregator, dd_run_check, tmp_path):
    state_file = tmp_path / 'smartd.EMPTY_DRIVE-SERIAL000.ata.state'
    state_file.write_text('')

    instance = {
        'smartd_state_dir': str(tmp_path),
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    # Empty state file = no SMART attributes parsed yet, should be UNKNOWN
    # rather than a silent OK.
    tags = ['device_model:EMPTY_DRIVE', 'serial_number:SERIAL000']
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.UNKNOWN, tags=tags)
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)


def test_check_state_dir_missing(aggregator, dd_run_check):
    instance = {
        'smartd_state_dir': '/definitely/does/not/exist',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    # CRITICAL with a message that points at the smartd -s config requirement.
    aggregator.assert_service_check('smartd.can_read', AgentCheck.CRITICAL)
    service_checks = aggregator.service_checks('smartd.can_read')
    assert any('-s <prefix>' in sc.message for sc in service_checks)


def test_check_state_dir_empty(aggregator, dd_run_check, tmp_path):
    # Directory exists but smartd is not writing state files into it.
    instance = {
        'smartd_state_dir': str(tmp_path),
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    aggregator.assert_service_check('smartd.can_read', AgentCheck.CRITICAL)
    service_checks = aggregator.service_checks('smartd.can_read')
    assert any('-s <prefix>' in sc.message for sc in service_checks)


def test_check_malformed_lines(aggregator, dd_run_check, tmp_path):
    state_file = tmp_path / 'smartd.TEST_DRIVE-SERIAL001.ata.state'
    state_file.write_text(
        '# comment line\n'
        'garbage line\n'
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = 201864314917\n'
        'ata-smart-attribute.0.bad_field = 999\n'
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    tags = ['device_model:TEST_DRIVE', 'serial_number:SERIAL001']
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour'):
        assert_smartd_metric(aggregator, 'smartd.{}'.format(metric), 0, tags)
    aggregator.assert_metric(
        'smartd.state_file_age_seconds', tags=tags, metric_type=AggregatorStub.GAUGE
    )
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.OK, tags=tags)
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)
    aggregator.assert_all_metrics_covered()


def test_check_unparseable_filename(aggregator, dd_run_check, tmp_path):
    state_file = tmp_path / 'smartd.bad-filename.state'
    state_file.write_text('ata-smart-attribute.0.id = 194\n')

    instance = {
        'smartd_state_dir': str(tmp_path),
        'file_pattern': 'smartd.*.state',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    # File is found so can_read is OK, but no per-drive metrics or disk_health
    # service check should be emitted for an unparseable filename.
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)
    assert aggregator.metrics('smartd.temperature') == []
    assert aggregator.service_checks('smartd.disk_health') == []


def test_device_name_resolution(aggregator, dd_run_check, tmp_path):
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    state_file = state_dir / 'smartd.DEV_DRIVE-SERIAL_ABC.ata.state'
    state_file.write_text(
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = 201864314917\n'
    )

    by_id = tmp_path / 'by-id'
    by_id.mkdir()
    # Mimic the real /dev/disk/by-id layout: a relative symlink pointing back
    # to the kernel device name, e.g. ../../sdx
    symlink = by_id / 'ata-DEV_DRIVE_SERIAL_ABC'
    os.symlink('../../sdx', symlink)

    instance = {
        'smartd_state_dir': str(state_dir),
        'dev_disk_by_id': str(by_id),
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    expected_tags = [
        'device_model:DEV_DRIVE',
        'serial_number:SERIAL_ABC',
        'device:/dev/sdx',
        'device_name:sdx',
    ]
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, expected_tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour'):
        assert_smartd_metric(aggregator, 'smartd.{}'.format(metric), 0, expected_tags)
    aggregator.assert_metric(
        'smartd.state_file_age_seconds', tags=expected_tags, metric_type=AggregatorStub.GAUGE
    )
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.OK, tags=expected_tags)
    aggregator.assert_all_metrics_covered()


def test_device_name_resolution_dashed_model(aggregator, dd_run_check, tmp_path):
    # Real-world case: smartd normalizes dashes in the hardware model to
    # underscores in the state file name, while /dev/disk/by-id preserves
    # the original dashes. We should still resolve the device by globbing
    # on the serial suffix.
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    state_file = state_dir / 'smartd.ST20000NM007D_3DJ103-ZVT5ZG8Q.ata.state'
    state_file.write_text(
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = 201864314917\n'
    )

    by_id = tmp_path / 'by-id'
    by_id.mkdir()
    # Dashes preserved in by-id (unlike the state file name)
    symlink = by_id / 'ata-ST20000NM007D-3DJ103_ZVT5ZG8Q'
    os.symlink('../../sdb', symlink)
    # Partition symlink that should NOT match (different suffix)
    os.symlink('../../sdb1', by_id / 'ata-ST20000NM007D-3DJ103_ZVT5ZG8Q-part1')

    instance = {
        'smartd_state_dir': str(state_dir),
        'dev_disk_by_id': str(by_id),
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    expected_tags = [
        'device_model:ST20000NM007D_3DJ103',
        'serial_number:ZVT5ZG8Q',
        'device:/dev/sdb',
        'device_name:sdb',
    ]
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, expected_tags)
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.OK, tags=expected_tags)


def test_device_name_missing_symlink(aggregator, dd_run_check, tmp_path):
    state_dir = tmp_path / 'state'
    state_dir.mkdir()
    state_file = state_dir / 'smartd.NODEV_DRIVE-SERIAL_XYZ.ata.state'
    state_file.write_text(
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = 201864314917\n'
    )

    by_id = tmp_path / 'empty-by-id'
    by_id.mkdir()

    instance = {
        'smartd_state_dir': str(state_dir),
        'dev_disk_by_id': str(by_id),
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    # No device/device_name tags when resolution fails, but metric still emitted
    expected_tags = ['device_model:NODEV_DRIVE', 'serial_number:SERIAL_XYZ']
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, expected_tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour'):
        assert_smartd_metric(aggregator, 'smartd.{}'.format(metric), 0, expected_tags)
    aggregator.assert_metric(
        'smartd.state_file_age_seconds', tags=expected_tags, metric_type=AggregatorStub.GAUGE
    )
    aggregator.assert_all_metrics_covered()


def test_custom_tags(aggregator, dd_run_check, tmp_path):
    state_file = tmp_path / 'smartd.TAG_DRIVE-SERIAL002.ata.state'
    state_file.write_text(
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = 201864314917\n'
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
        'tags': ['datacenter:us-east', 'rack:42'],
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    expected_tags = ['device_model:TAG_DRIVE', 'serial_number:SERIAL002', 'datacenter:us-east', 'rack:42']
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, expected_tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour'):
        assert_smartd_metric(aggregator, 'smartd.{}'.format(metric), 0, expected_tags)
    aggregator.assert_metric(
        'smartd.state_file_age_seconds', tags=expected_tags, metric_type=AggregatorStub.GAUGE
    )
    # can_read should also carry the instance tags so users can scope
    # alerts by datacenter/rack.
    aggregator.assert_service_check(
        'smartd.can_read', AgentCheck.OK, tags=['datacenter:us-east', 'rack:42']
    )
    aggregator.assert_all_metrics_covered()


def test_monotonic_count_submits_absolute_value(aggregator, dd_run_check, tmp_path):
    """Pin the contract: monotonic attributes are submitted as
    monotonic_count with the drive's absolute raw value. The Datadog
    aggregator drops the first sample per (metric, tag-set) after a
    restart and emits deltas from there — so the check must hand it the
    absolute counter, not a pre-computed delta.
    """
    state_file = tmp_path / 'smartd.MONO_DRIVE-SERIAL_MONO.ata.state'
    state_file.write_text(
        # power_on_hours (ID 9): monotonic
        'ata-smart-attribute.0.id = 9\n'
        'ata-smart-attribute.0.val = 100\n'
        'ata-smart-attribute.0.raw = 12345\n'
        # temperature (ID 194): gauge (not monotonic)
        'ata-smart-attribute.1.id = 194\n'
        'ata-smart-attribute.1.val = 160\n'
        'ata-smart-attribute.1.raw = 37\n'
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
        'dev_disk_by_id': '/nonexistent/by-id',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    tags = ['device_model:MONO_DRIVE', 'serial_number:SERIAL_MONO']
    aggregator.assert_metric(
        'smartd.power_on_hours',
        value=12345,
        tags=tags,
        metric_type=AggregatorStub.MONOTONIC_COUNT,
    )
    aggregator.assert_metric(
        'smartd.temperature',
        value=37,
        tags=tags,
        metric_type=AggregatorStub.GAUGE,
    )


def test_disk_health_critical_on_zero_normalized_value(aggregator, dd_run_check, tmp_path):
    """If any monitored attribute's normalized value drops to 0, the drive
    is considered failing and disk_health must be CRITICAL (not WARNING,
    even if warning-class attributes are also non-zero)."""
    state_file = tmp_path / 'smartd.FAIL_DRIVE-SERIAL_FAIL.ata.state'
    state_file.write_text(
        # reallocated_sectors (ID 5): both val==0 (critical) and raw > 0
        'ata-smart-attribute.0.id = 5\n'
        'ata-smart-attribute.0.val = 0\n'
        'ata-smart-attribute.0.raw = 99\n'
        # temperature for basic sanity
        'ata-smart-attribute.1.id = 194\n'
        'ata-smart-attribute.1.val = 160\n'
        'ata-smart-attribute.1.raw = 37\n'
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
        'dev_disk_by_id': '/nonexistent/by-id',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    tags = ['device_model:FAIL_DRIVE', 'serial_number:SERIAL_FAIL']
    aggregator.assert_service_check('smartd.disk_health', AgentCheck.CRITICAL, tags=tags)


def test_temperature_raw_masking(aggregator, dd_run_check, tmp_path):
    """Vendors pack auxiliary data (min/max, other sensors) into the
    upper bytes of SMART ID 194's raw value. The check must mask down
    to the lowest byte, not report the full packed integer."""
    state_file = tmp_path / 'smartd.TEMP_DRIVE-SERIAL_TEMP.ata.state'
    # 0x0020001E0025 — Seagate-style packing with current temp = 0x25 (37C)
    # in the lowest byte and min/max in the upper bytes.
    packed_raw = 0x0020001E0025
    state_file.write_text(
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = {}\n'.format(packed_raw)
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
        'dev_disk_by_id': '/nonexistent/by-id',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    tags = ['device_model:TEMP_DRIVE', 'serial_number:SERIAL_TEMP']
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, tags)


def test_disk_health_critical_on_parse_exception(aggregator, dd_run_check, tmp_path, monkeypatch):
    """If the state file parser raises (simulating a drive physically
    failing mid-write and producing corrupt content), the check must
    downgrade the drive's disk_health to CRITICAL with the filename in
    the message rather than propagating the exception and aborting the
    whole check cycle."""
    state_file = tmp_path / 'smartd.BROKEN_DRIVE-SERIAL_BRK.ata.state'
    state_file.write_text('ata-smart-attribute.0.id = 194\n')

    instance = {
        'smartd_state_dir': str(tmp_path),
        'dev_disk_by_id': '/nonexistent/by-id',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])

    def boom(self, path):
        raise ValueError('simulated truncated state file')

    monkeypatch.setattr(SmartdCheck, '_parse_state_file', boom)
    dd_run_check(check)

    tags = ['device_model:BROKEN_DRIVE', 'serial_number:SERIAL_BRK']
    service_checks = aggregator.service_checks('smartd.disk_health')
    assert len(service_checks) == 1
    sc = service_checks[0]
    assert sc.status == AgentCheck.CRITICAL
    assert sc.tags == tags
    assert 'smartd.BROKEN_DRIVE-SERIAL_BRK.ata.state' in sc.message
    assert 'simulated truncated state file' in sc.message
    # can_read remains OK — the parse failure is a per-drive problem, not
    # a "smartd not running" problem.
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)


def test_disk_health_critical_beats_warning(aggregator, dd_run_check, tmp_path):
    """When a drive has both a CRITICAL-level attribute (val==0) and a
    WARNING-level attribute (raw>0 in WARNING_ATTRIBUTES), the service
    check must be CRITICAL and the message must mention the critical
    attribute — not silently flip to WARNING depending on dict iteration
    order."""
    state_file = tmp_path / 'smartd.MIXED_DRIVE-SERIAL_MIX.ata.state'
    state_file.write_text(
        # reallocated_sectors (ID 5): val==0 → CRITICAL
        'ata-smart-attribute.0.id = 5\n'
        'ata-smart-attribute.0.val = 0\n'
        'ata-smart-attribute.0.raw = 50\n'
        # current_pending_sectors (ID 197): raw>0 → WARNING on its own
        'ata-smart-attribute.1.id = 197\n'
        'ata-smart-attribute.1.val = 100\n'
        'ata-smart-attribute.1.raw = 3\n'
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
        'dev_disk_by_id': '/nonexistent/by-id',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    tags = ['device_model:MIXED_DRIVE', 'serial_number:SERIAL_MIX']
    service_checks = aggregator.service_checks('smartd.disk_health')
    assert len(service_checks) == 1
    sc = service_checks[0]
    assert sc.status == AgentCheck.CRITICAL
    assert 'Attribute 5' in sc.message


def test_non_ata_state_file_is_skipped(aggregator, dd_run_check, tmp_path):
    """NVMe and SCSI state files use entirely different key namespaces.
    Until those parsers exist, the check must skip them cleanly — no
    disk_health service check, no metrics — rather than opening them and
    emitting a misleading UNKNOWN."""
    # An NVMe state file next to an ATA one, to prove the ATA path still
    # works and the NVMe file is specifically the one being skipped.
    (tmp_path / 'smartd.NVME_DRIVE-SERIAL_NVME.nvme.state').write_text(
        'nvme-smart-health-information.temperature = 40\n'
    )
    (tmp_path / 'smartd.ATA_DRIVE-SERIAL_ATA.ata.state').write_text(
        'ata-smart-attribute.0.id = 194\n'
        'ata-smart-attribute.0.val = 160\n'
        'ata-smart-attribute.0.raw = 37\n'
    )

    instance = {
        'smartd_state_dir': str(tmp_path),
        'dev_disk_by_id': '/nonexistent/by-id',
    }
    check = SmartdCheck(CHECK_NAME, {}, [instance])
    dd_run_check(check)

    # ATA drive reports as usual
    ata_tags = ['device_model:ATA_DRIVE', 'serial_number:SERIAL_ATA']
    assert_smartd_metric(aggregator, 'smartd.temperature', 37, ata_tags)

    # NVMe drive: no metrics or service check at all
    nvme_tags = ['device_model:NVME_DRIVE', 'serial_number:SERIAL_NVME']
    for sc in aggregator.service_checks('smartd.disk_health'):
        assert 'device_model:NVME_DRIVE' not in sc.tags
    for metric_name in ('smartd.temperature', 'smartd.state_file_age_seconds'):
        assert not any(
            'device_model:NVME_DRIVE' in m.tags
            for m in aggregator.metrics(metric_name)
        )
    # can_read still OK because the ATA file was parsed successfully
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)
