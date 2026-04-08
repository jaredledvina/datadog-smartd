# CHANGELOG - smartd

<!-- towncrier release notes start -->

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
