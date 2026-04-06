# snmp-poller

Concurrent SNMPv3 poller built on [pysnmp](https://pysnmp.readthedocs.io) and [asyncio](https://docs.python.org/3/library/asyncio.html).

Polls multiple hosts in parallel, with device groups that define which OIDs to query per host class.

## Install

```
pip install .
```

For development (includes pytest):

```
pip install -e ".[dev]"
```

## Usage

```
snmp-poller -s <snmp_auth.yml> -l <hosts.csv> -o <oids.yml>
```

| Flag | Required | Description |
|------|----------|-------------|
| `-s` | yes | SNMPv3 credentials (YAML) |
| `-l` | yes | Host list with group assignments (CSV) |
| `-o` | yes | OID definitions per group (YAML) |
| `-f` | no | JSON output file (default: `/var/log/snmp_poll/snmp_poll.log`) |
| `--log-dir` | no | Application log directory (default: `/var/log/snmp_poll`) |
| `--engine-pool-size` | no | SNMP engines per worker (default: 5) |
| `--workers` | no | Worker processes for parallel polling (default: 1) |

## Configuration

See `examples/` for sample files.

**SNMPv3 credentials** (`-s`):

```yaml
userName: myuser
authKey: my_auth_key
privKey: my_priv_key
localAddress: 192.168.1.100
```

**Host list** (`-l`):

```csv
192.168.1.1,linux_servers
192.168.1.2,linux_servers
10.0.0.1,network_switches
```

**OID definitions** (`-o`) — each group defines the OIDs to poll and their output types:

```yaml
linux_servers:
  - name: ssCpuIdle
    oid: .1.3.6.1.4.1.2021.11.11.0
    type: float
  - name: memAvailReal
    oid: .1.3.6.1.4.1.2021.4.6.0
    type: int

network_switches:
  - name: ifInOctets
    oid: .1.3.6.1.2.1.2.2.1.10.1
    type: int
  - name: sysUpTime
    oid: .1.3.6.1.2.1.1.3.0
    type: str
```

Any number of groups and any number of OIDs per group are supported.

## Scaling to 10,000+ hosts

By default, snmp-poller runs in a single process. For large-scale
polling, use `--workers` to distribute hosts across multiple processes,
each with its own asyncio event loop and engine pool:

```
# 10 processes × 100 engines = handles ~10,000 hosts
snmp-poller -s auth.yml -l hosts.csv -o oids.yml \
    --workers 10 --engine-pool-size 100
```

Each worker polls its hosts concurrently. Results are collected
centrally by the supervisor process — no file contention.

## Output

Each polled host produces a JSON record sent to syslog and written to the output file:

```json
{
  "device": "192.168.1.1",
  "snmp_data_grp": "linux_servers",
  "poller_instance": "snmp_poll_nix",
  "ssCpuIdle": 95.0,
  "memAvailReal": 2048000
}
```

Field names and types come from the OID config — nothing is hardcoded.

## Tests

```
pytest -m "not integration"
```

### Integration tests

Integration tests poll real SNMP agents running in containers. Requires podman.

```
# Build the test container (once)
podman build -t snmpd-test -f tests/integration/Containerfile tests/integration/

# Run integration tests
pytest tests/integration/ -m integration

# Run everything
pytest
```

## License

MIT
