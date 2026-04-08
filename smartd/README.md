# smartd

## Overview

This integration monitors [S.M.A.R.T.][1] disk health by reading state files written by the [smartd][2] daemon (part of [smartmontools][3]). It collects key disk health attributes such as temperature, reallocated sectors, power-on hours, and pending sector counts, and reports the overall health status of each drive as a service check.

Unlike other approaches that shell out to `smartctl` (which requires root privileges), this integration reads the state files that `smartd` already maintains, making it work without any privilege escalation.

## Setup

### Prerequisites

- The `smartd` daemon must be running and writing state files (default location: `/var/lib/smartmontools/`).
- The `dd-agent` user must have read access to the state files (they are typically world-readable with `644` permissions).

### Installation

For development, install the check in the Datadog Agent's Python environment:

```bash
datadog-agent integration install -e /path/to/smartd
```

For production, copy the check file and configuration:

```bash
cp datadog_checks/smartd/check.py /etc/datadog-agent/checks.d/smartd.py
mkdir -p /etc/datadog-agent/conf.d/smartd.d
cp datadog_checks/smartd/data/conf.yaml.example /etc/datadog-agent/conf.d/smartd.d/conf.yaml
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

**smartd.disk_health**: Returns `OK` if the drive is healthy, `WARNING` if reallocated sectors, pending sectors, or offline uncorrectable counts are non-zero, `CRITICAL` if a normalized attribute value reaches 0.

**smartd.can_read**: Returns `OK` if smartd state files were found and parsed successfully, `CRITICAL` otherwise.

### Events

The smartd integration does not include any events.

## Support

For help, open an issue on the [GitHub repository][7].

[1]: https://en.wikipedia.org/wiki/Self-Monitoring,_Analysis_and_Reporting_Technology
[2]: https://www.smartmontools.org/wiki/Smartd
[3]: https://www.smartmontools.org/
[4]: https://docs.datadoghq.com/agent/guide/agent-commands/#start-stop-and-restart-the-agent
[5]: https://docs.datadoghq.com/agent/guide/agent-commands/#agent-status-and-information
[6]: https://github.com/DataDog/integrations-extras/blob/master/smartd/metadata.csv
[7]: https://github.com/DataDog/integrations-extras
