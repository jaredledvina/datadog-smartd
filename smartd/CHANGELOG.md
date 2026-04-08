# CHANGELOG - smartd

<!-- towncrier release notes start -->

## 0.1.5 / 2026-04-08

***Added***:

* Collect additional SMART attributes: `spin_up_time` (3), `start_stop_count` (4), `wear_leveling_count` (177), `used_reserved_block_count` (179), `program_fail_count` (181), `erase_fail_count` (182), `reported_uncorrectable_errors` (187), `command_timeout` (188), `airflow_temperature` (190), `power_off_retract_count` (192), `load_cycle_count` (193), `por_recovery_count` (235), `head_flying_hours` (240), `total_lbas_written` (241), and `total_lbas_read` (242). SSD-specific and enterprise-drive attributes are now surfaced when present.
* Collect top-level state-file fields as metrics: `smartd.ata_error_count`, `smartd.self_test_errors`, and `smartd.self_test_last_err_hour`. smartd only writes these when non-zero, so absent values are reported as 0 to keep time series continuous. `scheduled-test-next-check` is intentionally not exposed because it is a Unix timestamp, which does not make a useful gauge time series.
* `reported_uncorrectable_errors` (ID 187) is now treated as a warning attribute alongside reallocated/pending/offline-uncorrectable sectors.

***Fixed***:

* Device name resolution now matches `/dev/disk/by-id/ata-*_<SERIAL>` by serial suffix instead of building `ata-<MODEL>_<SERIAL>`. smartd normalizes dashes in the hardware model to underscores when constructing state file names, while `/dev/disk/by-id` preserves the original dashes — the old builder failed to resolve device names for drives whose model contains dashes (e.g. Seagate `ST20000NM007D-3DJ103`).

## 0.1.4 / 2026-04-08

***Added***:

* README Prerequisites section documenting that smartd must be launched with `-s <prefix>` to persist per-drive state files, with distro-specific notes (Debian/Ubuntu enables it by default, Arch does not).
* `smartd.disk_health` now reports UNKNOWN (instead of silently OK) when a state file exists but contains no SMART attributes yet — typically the window between smartd starting and its first poll cycle.

***Fixed***:

* `smartd.can_read` CRITICAL messages now explain the smartd configuration requirement and point at the README Prerequisites section, distinguishing between "state directory does not exist" and "state directory is empty".

## 0.1.3 / 2026-04-08

***Added***:

* Resolve each drive's kernel device name via `/dev/disk/by-id/ata-<MODEL>_<SERIAL>` and attach `device:/dev/<name>` and `device_name:<name>` tags to metrics and service checks, matching the convention used by the core `system.disk.*` metrics.
* New `dev_disk_by_id` instance option (default `/dev/disk/by-id`) to override the by-id lookup directory.

## 0.1.2 / 2026-04-08

***Fixed***:

* Correct `homepage`, `Source`, and documentation links to point at `jaredledvina/datadog-smartd` instead of `DataDog/integrations-extras`.
* Set author name to `Jared Ledvina` in `manifest.json` and `pyproject.toml`, and add a copyright holder to `LICENSE`.
* Remove `support_email` from `manifest.json` (self-hosted release; GitHub Issues is the support channel).
* Rewrite README installation section to document the real PyPI + `datadog-agent integration install --local-wheel` flow.

## 0.1.1 / 2026-04-05

***Fixed***:

* Relax `requires-python` from `>=3.13` to `>=3.9` so the wheel is installable into the Datadog Agent's embedded Python 3.12.

## 0.1.0 / 2026-04-05

***Added***:

* Initial release of smartd integration for S.M.A.R.T. disk health monitoring via smartd state files.
* Collects 10 SMART attributes as gauges: raw read error rate, reallocated sectors, power-on hours, spin retry count, power cycle count, temperature, reallocated event count, current pending sectors, offline uncorrectable, and UDMA CRC error count.
* Emits `smartd.disk_health` and `smartd.can_read` service checks.
