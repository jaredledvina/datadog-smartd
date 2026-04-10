# smartd

## Overview

This integration monitors [S.M.A.R.T.][1] disk health by reading state files written by the [smartd][2] daemon (part of [smartmontools][3]). It collects key disk health attributes such as temperature, reallocated sectors, power-on hours, and pending sector counts, and reports the overall health status of each drive as a service check.

Unlike other approaches that shell out to `smartctl` (which requires root privileges), this integration reads the state files that `smartd` already maintains, making it work without any privilege escalation.

## Setup

### Prerequisites

#### smartd must be persisting state files

This integration reads the per-drive state files that `smartd` writes on every poll cycle. **smartd does not persist state files by default** — it must be launched with the `-s <prefix>` argument, where `<prefix>` is usually `/var/lib/smartmontools/smartd.` so that files land as `/var/lib/smartmontools/smartd.<MODEL>-<SERIAL>.<type>.state`.

Distros handle this differently:

- **Debian / Ubuntu**: the packaged systemd unit already passes `-s /var/lib/smartmontools/smartd.` via `/etc/default/smartmontools`. Nothing to do.
- **Arch Linux** (and anything else running smartd as just `smartd -n`): state persistence is **not** enabled by default. Create `/etc/conf.d/smartd` with:
  ```
  SMARTD_ARGS='-s /var/lib/smartmontools/smartd.'
  ```
  Then `mkdir -p /var/lib/smartmontools && systemctl restart smartd`. State files will start appearing on the next poll cycle (default every 30 minutes).

To verify smartd is persisting state, wait a poll cycle after starting smartd and check that `/var/lib/smartmontools/smartd.*.state` files exist and contain lines like `ata-smart-attribute.0.id = 1`.

If the integration can't find any state files it will emit a CRITICAL `smartd.can_read` service check with a message pointing back to this section. If a state file exists but has no SMART attribute data yet (normal right after smartd starts), `smartd.disk_health` will report UNKNOWN for that drive until the next poll cycle populates the file.

#### File permissions

The `dd-agent` user must have read access to the state files. They are typically world-readable with `644` permissions, so no special configuration is needed.

### Installation

The integration is published to [PyPI][8]. The Datadog Agent does not use public PyPI directly, so install it by downloading the wheel and handing it to the Agent's `integration install` command.

```bash
# Download the wheel using the Agent's embedded pip
/opt/datadog-agent/embedded/bin/pip download --no-deps -d /tmp datadog-smartd

# Install the downloaded wheel into the Agent
datadog-agent integration install --local-wheel /tmp/datadog_smartd-*.whl

# Drop the example config into place and edit as needed
mkdir -p /etc/datadog-agent/conf.d/smartd.d
cp /opt/datadog-agent/embedded/lib/python*/site-packages/datadog_checks/smartd/data/conf.yaml.example \
   /etc/datadog-agent/conf.d/smartd.d/conf.yaml
```

### Configuration

Edit `/etc/datadog-agent/conf.d/smartd.d/conf.yaml` to configure the check:

```yaml
init_config:

instances:
  - smartd_state_dir: /var/lib/smartmontools
    min_collection_interval: 120
```

Then [restart the Agent][4].

### Validation

Run the [Agent's status subcommand][5] and look for `smartd` under the Checks section:

```bash
datadog-agent status
```

Or run the check directly:

```bash
datadog-agent check smartd
```

## Data Collected

### Metrics

See [metadata.csv][6] for a list of metrics provided by this integration.

### Service Checks

**smartd.disk_health**: Returns `OK` if the drive is healthy, `WARNING` if reallocated sectors, pending sectors, offline uncorrectable counts, or reported uncorrectable errors are non-zero, `CRITICAL` if a normalized attribute value reaches 0.

**smartd.can_read**: Returns `OK` if smartd state files were found and parsed successfully, `CRITICAL` otherwise.

### Events

The smartd integration does not include any events.

## Behavior notes

A few things are worth knowing before writing monitors on these metrics.

### Monotonic counters have a one-interval warm-up after agent restart

Metrics like `smartd.power_on_hours`, `smartd.reallocated_sectors`, `smartd.udma_crc_error_count`, `smartd.ata_error_count`, and all the other `count`-type metrics in `metadata.csv` are emitted as monotonic counters. The Datadog Agent drops the first sample for each `(metric, tag-set)` pair after a restart to establish a baseline, then emits the per-interval delta from the second sample onwards. In practice this means you will see "no data" for the first check cycle after an agent restart for any counter metric. This is normal and expected — it's what makes trivial rate queries like "errors in the last 5 minutes" work without any `diff()` gymnastics in the monitor.

### `disk_health = CRITICAL` is post-mortem, not predictive

The check flips to CRITICAL when any SMART attribute's *normalized* value (`val`) reaches 0. By the time that happens the drive's own firmware has almost certainly already failed the drive. This is useful as a "confirmed-dead, replace now" signal but is **not** a predictive "drive is going to fail soon" signal. For predictive monitoring, alert on `smartd.disk_health = WARNING` (which fires as soon as `reallocated_sectors`, `current_pending_sectors`, `offline_uncorrectable`, or `reported_uncorrectable_errors` become non-zero — the Backblaze-validated early-warning attributes), or write your own threshold monitors on those metrics directly.

### Several raw values are vendor-encoded

`smartd.temperature` reports the lowest byte of SMART attribute 194's raw value, which is the current temperature in °C on every drive we've tested (Seagate, HGST, Hitachi, Samsung SSD). Some vendors pack minimum/maximum temperatures in the upper bytes of the same raw int, which this check ignores.

`smartd.spin_up_time`, `smartd.total_lbas_written`, and `smartd.total_lbas_read` are emitted as the drive-reported raw uint, with no vendor-specific decoding. Depending on the drive, `total_lbas_*` may be in raw LBA units or vendor-chosen multiples (commonly 32 MiB or 64 MiB chunks on Samsung SSDs), so do not multiply by sector size to derive TB-written without first confirming the encoding for your specific drive model.

`smartd.power_on_hours` is in hours on every drive we've tested but some older drives reported in minutes — double-check against `smartctl -A` if a drive shows unexpectedly large values.

### Non-ATA state files are currently ignored

Only `.ata.state` files are parsed. If smartd writes `.nvme.state` (NVMe drives) or `.scsi.state` (SAS/SCSI drives), the check logs the bus type once at `INFO` level and skips the file — no metrics or service checks are emitted for those drives. NVMe and SCSI support is planned for a future release.

## Support

For help, open an issue on the [GitHub repository][7].

[1]: https://en.wikipedia.org/wiki/Self-Monitoring,_Analysis_and_Reporting_Technology
[2]: https://www.smartmontools.org/wiki/Smartd
[3]: https://www.smartmontools.org/
[4]: https://docs.datadoghq.com/agent/guide/agent-commands/#start-stop-and-restart-the-agent
[5]: https://docs.datadoghq.com/agent/guide/agent-commands/#agent-status-and-information
[6]: https://github.com/jaredledvina/datadog-smartd/blob/main/smartd/metadata.csv
[7]: https://github.com/jaredledvina/datadog-smartd/issues
[8]: https://pypi.org/project/datadog-smartd/
