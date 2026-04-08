import os
from unittest.mock import patch

import pytest

from datadog_checks.base import AgentCheck
from datadog_checks.smartd import SmartdCheck

from .common import (
    CHECK_NAME,
    DEGRADED_TAGS,
    FIXTURE_DIR,
    HEALTHY_TAGS,
    INSTANCE,
)

pytestmark = pytest.mark.unit


def test_check_healthy_and_degraded(aggregator, dd_run_check):
    check = SmartdCheck(CHECK_NAME, {}, [INSTANCE])
    dd_run_check(check)

    # Healthy drive attribute metrics
    aggregator.assert_metric('smartd.raw_read_error_rate', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.spin_up_time', value=38683869672, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.start_stop_count', value=29, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.reallocated_sectors', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.power_on_hours', value=91000, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.spin_retry_count', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.power_cycle_count', value=29, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.power_off_retract_count', value=1168, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.load_cycle_count', value=1168, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.temperature', value=37, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.reallocated_event_count', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.current_pending_sectors', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.offline_uncorrectable', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.udma_crc_error_count', value=0, tags=HEALTHY_TAGS)
    # Healthy drive top-level metrics (all default to 0)
    aggregator.assert_metric('smartd.ata_error_count', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.self_test_errors', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.self_test_last_err_hour', value=0, tags=HEALTHY_TAGS)
    aggregator.assert_metric('smartd.scheduled_test_next_check', value=0, tags=HEALTHY_TAGS)

    # Degraded drive attribute metrics
    aggregator.assert_metric('smartd.raw_read_error_rate', value=12, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.spin_up_time', value=42949672960, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.start_stop_count', value=45, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.reallocated_sectors', value=16, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.power_on_hours', value=105000, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.spin_retry_count', value=0, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.power_cycle_count', value=45, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.power_off_retract_count', value=2000, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.load_cycle_count', value=2000, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.temperature', value=41, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.reallocated_event_count', value=16, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.current_pending_sectors', value=2, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.offline_uncorrectable', value=0, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.udma_crc_error_count', value=3, tags=DEGRADED_TAGS)
    # Degraded drive top-level metrics (three populated from fixture)
    aggregator.assert_metric('smartd.ata_error_count', value=42, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.self_test_errors', value=1, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.self_test_last_err_hour', value=98765, tags=DEGRADED_TAGS)
    aggregator.assert_metric('smartd.scheduled_test_next_check', value=0, tags=DEGRADED_TAGS)

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
    aggregator.assert_metric('smartd.temperature', value=37, tags=tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour', 'scheduled_test_next_check'):
        aggregator.assert_metric('smartd.{}'.format(metric), value=0, tags=tags)
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

    # File is found so can_read is OK, but no metrics emitted for unparseable filename
    aggregator.assert_service_check('smartd.can_read', AgentCheck.OK)


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
    aggregator.assert_metric('smartd.temperature', value=37, tags=expected_tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour', 'scheduled_test_next_check'):
        aggregator.assert_metric('smartd.{}'.format(metric), value=0, tags=expected_tags)
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
    aggregator.assert_metric('smartd.temperature', value=37, tags=expected_tags)
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
    aggregator.assert_metric('smartd.temperature', value=37, tags=expected_tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour', 'scheduled_test_next_check'):
        aggregator.assert_metric('smartd.{}'.format(metric), value=0, tags=expected_tags)
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
    aggregator.assert_metric('smartd.temperature', value=37, tags=expected_tags)
    for metric in ('ata_error_count', 'self_test_errors', 'self_test_last_err_hour', 'scheduled_test_next_check'):
        aggregator.assert_metric('smartd.{}'.format(metric), value=0, tags=expected_tags)
    aggregator.assert_all_metrics_covered()
