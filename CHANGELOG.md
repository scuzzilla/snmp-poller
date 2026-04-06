# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.4.0] - 2026-04-06

### Added
- **GitHub Actions CI** — runs flake8 lint and unit tests on every push/PR to main, across Python 3.12 and 3.13
- **Graceful shutdown** — handles SIGINT (Ctrl+C) and SIGTERM in both single-process and multiprocessing modes:
  - Single-process: `KeyboardInterrupt` caught, syslog closed cleanly
  - Multiprocessing: signal handler terminates all worker processes, drains remaining results, joins workers with timeout

## [0.3.0] - 2026-04-06

### Changed
- **Migrated from pysnmp v4 to v7** — removes the `asyncore` dependency that blocked Python 3.12+. The app now runs on Python 3.12, 3.13, and 3.14.
- All pysnmp imports updated to `pysnmp.hlapi.v3arch.asyncio`
- `getCmd` renamed to `get_cmd` (pysnmp v7 snake_case convention)
- `UdpTransportTarget` now uses async `.create()` factory + `set_local_address()`
- `build_snmp_request()` is now async (transport creation requires await in v7)
- `UsmUserData` uses positional arguments (v7 convention)
- Removed separate `integration` optional dependency group — main `pysnmp>=7` covers both app and integration tests

### Performance
- Single-host baseline: 1.3ms → 1.0ms (23% faster)
- Engine pool of 5 at 50 hosts: 498ms → 477ms (4% faster)
- Engine pool of 10 at 50 hosts: 978ms → 782ms (20% faster)
- Engine pool of 25 at 50 hosts: 2,103ms → 1,584ms (25% faster)

## [0.2.0] - 2026-04-06

### Added
- **Multiprocessing support** — `--workers N` distributes hosts across N worker processes, each with its own asyncio event loop and SNMP engine pool. Enables polling 10,000+ hosts in parallel.
- `poll_host()` coroutine — returns result dict instead of writing to file, used by worker processes
- `_partition_hosts()` — splits host records into roughly-equal chunks for worker distribution
- `_worker_process()` — child process entry point with independent engine pool and event loop
- `_run_multiprocess()` — supervisor that spawns workers, collects results via `multiprocessing.Queue`, writes output centrally (no file contention)
- Scalability benchmark suite (`tests/integration/test_scalability.py`) — 50 containers, compares engine pool strategies, measures concurrency speedup
- Unit tests for `_partition_hosts` (5 tests) and `poll_host` (4 tests)
- CLI tests for `--workers` flag (4 tests)

### Changed
- `--engine-pool-size` now applies per worker process (was global)
- `_build_result()` extracted from `get_async` to share result-building logic between single-process and multiprocessing paths
- `main()` branches on `--workers`: 1 = existing single-process path (unchanged), >1 = multiprocessing

## [0.1.0] - 2026-04-06

### Added
- `pyproject.toml` — project is now pip-installable (`pip install .` or `pip install -e .[dev]`)
- `snmp-poller` console script entry point — installed via pip, runs `snmp_poller.poller:main`
- `src/snmp_poller/` package layout (PEP 621 src-layout):
  - `__init__.py` — package marker
  - `__main__.py` — supports `python -m snmp_poller`
  - `poller.py` — main polling logic (was `snmp-poller.py`)
  - `snmp_init.py` — SNMP initialization class (was `base/pysnmp_init_class.py`)
  - `cli.py` — CLI argument parsing (was `base/cli_params.py`)
  - `data_loader.py` — YAML/CSV loaders (was `utils/data_loader.py`)
  - `logging.py` — logging setup (was `utils/logging.py`)
- `main()` function and `if __name__ == '__main__':` guard — module can now be imported without side effects
- `build_snmp_request()` function — encapsulates SNMP request construction for any group
- `TYPE_CASTERS` mapping — config-driven type casting (`int`, `float`, `str`) for polled values
- Config-driven OID group system — groups, OID names, OID values, and types are all defined in `nix_oids_data.yml`
- Test suite (`tests/test_snmp_poller.py`) with 16 tests covering:
  - Request building logic per group
  - Async polling success and error paths
  - JSON output structure validation per group
  - Type casting from config
  - Concurrency scalability (50 hosts with simulated latency)
  - Partial failure isolation
  - Mixed-group concurrent polling
- `tests/__init__.py` package marker
- `-f` CLI option for configurable JSON output file path (default: `/var/log/snmp_poll/snmp_poll.log`)
- `--log-dir` CLI option for configurable application log directory (default: `/var/log/snmp_poll`)
- Log directory auto-created at startup if it doesn't exist (`os.makedirs` with `exist_ok=True`)
- `examples/` directory with sample config files (`snmp_auth.yml`, `oids.yml`, `hosts.csv`)
- Integration test suite (`tests/integration/`) with real SNMP agents in podman containers:
  - Containerfile + snmpd.conf for SNMPv3 test agent (Alpine + net-snmp)
  - 7 integration tests: single OID, multi-OID, auth failure, nonexistent OID, concurrent multi-agent polling, JSON output format
  - `pytest.mark.integration` marker for selective execution
- Unit tests for `cli.py` (8 tests), `data_loader.py` (8 tests), `logging.py` (5 tests) — total 48 tests, 97% coverage

### Changed
- `PySnmpInit` class redesigned — session-level objects (engine, credentials, context) created once in `__init__`; per-request objects (transport targets, object types) are stateless factory methods that no longer mutate `self`; removed redundant double-stored private attributes, dead class-level `None` attributes, and broken constructor calls with `None` arguments
- `cli.py` rewritten — file extension validation now uses `path.splitext()` with per-argument expected extensions; error reporting uses `parser.error()` instead of `print()` + boolean flags; imports moved to module level; renamed `daisy_hosts` to `hosts_file`; `cli_params()` no longer requires `app_base_path` argument
- `data_loader.py` — added error handling for malformed CSV rows, strips whitespace from host/group values, skips blank lines, fixed return type hint (`list` -> `dict`), imports moved to module level
- `logging.py` — guards against duplicate handlers when called multiple times, uses stable logger name `snmp_poller`, imports moved to module level
- Restructured project from flat layout to pip-installable `src/` layout
- Renamed `snmp-poller.py` to `snmp_poller.py` — hyphens in Python filenames break standard imports
- Renamed log paths from `snmp-poll-*` to `snmp_poll_*` for naming consistency:
  - `snmp-poll-app.log` -> `snmp_poll_app.log`
  - `/var/log/snmp-poll/snmp-poll.log` -> `/var/log/snmp_poll/snmp_poll.log`
- Renamed `poller_instance` value from `snmp-poll-nix` to `snmp_poll_nix`
- OID config format (`nix_oids_data.yml`) redesigned:
  - Groups are now named descriptively (`linux_servers`, `network_switches` instead of `GRP_A`, `GRP_B`)
  - Each OID entry has `name`, `oid`, and `type` fields
  - Any number of groups and any number of OIDs per group are supported
- CSV host records now reference group names directly (`linux_servers` instead of `A`)
- `get_async()` now receives all dependencies as arguments instead of relying on module-level globals
- JSON output fields are now generated dynamically from OID config `name` keys (no longer hardcoded)
- `syslog.openlog()` moved from per-host loop to once in `main()`, with matching `syslog.closelog()`
- Replaced `asyncio.wait()` (deprecated) with `asyncio.gather()`
- Error paths in `get_async()` use early returns instead of nested `if/else`
- String formatting standardized to f-strings (replaced `%` formatting)

### Removed
- Old flat file structure (`base/`, `utils/` directories) — replaced by `src/snmp_poller/` package
- `MAX_OIDS_GRP_A` / `MAX_OIDS_GRP_B` constants — no longer needed with config-driven groups
- Hardcoded `GRP_` prefix convention for group names
- Hardcoded `oid0.ssCpuIdle` / `oid1.memAvailReal` JSON output keys
- All commented-out debug code (print statements, CSV encoding block, timing block)
- Unused `import time`
- Unused `import sys` (from main module)
- Duplicate GRP_A/GRP_B code blocks (DRY violation)
- Hardcoded output log path `/var/log/snmp_poll/snmp_poll.log` — now configurable via `-f` flag
- `logs/` directory and stub READMEs in `csv/`, `data/`, `logs/` — no longer shipped with the project
- `requirements.txt` — replaced by `pyproject.toml` dependencies
- Venv artifacts from project root (`bin/`, `lib/`, `lib64/`, `include/`, `share/`, `pyvenv.cfg`)
- `csv/` and `data/` directories — sample configs moved to `examples/`

### Fixed
- **Bug**: CLI extension validation (`cli.py` line 83) used substring matching (`if ext in filename`) instead of actual extension check — a file named `csvdata.txt` would pass. Now uses `path.splitext()` and validates each file gets the correct extension (`.yml` for `-s`/`-o`, `.csv` for `-l`)
- Typo: `unhadled` -> `unhandled` in device group error message
