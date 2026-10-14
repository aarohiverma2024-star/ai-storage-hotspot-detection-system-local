# YCSB Integration

YCSB (Yahoo! Cloud Serving Benchmark) is a **workload generator**, not a database.

## Status: CONFIGURED (official YCSB 0.17.0, Java 17)

- `YCSB_HOME=/opt/ycsb` — official release `ycsb-0.17.0.tar.gz` from github.com/brianfrankcooper/YCSB/releases
- Java: OpenJDK 17 (installed via `apt-get install default-jre-headless`)
- Launcher: `bin/ycsb.sh` (the 0.17.0 Python launcher `bin/ycsb` is Python-2 only; the bundled shell launcher is used instead)
- Binding: `basic` (prints operations; requires no external DB) — real YCSB core engine, real workload files (`workloads/workloada` … `workloadf`), real measured output

`GET /api/v1/ycsb/validate` → real detection: `{ ycsb_installed: true, ycsb_version: "0.17.0", java_version: "17.0.20.1" }`

## Executing real YCSB

`POST /api/v1/ycsb/run` with `{ workload, record_count, operation_count, threads, extra_props }` executes the actual CLI:

```
sh /opt/ycsb/bin/ycsb.sh run basic -P /opt/ycsb/workloads/workloada -p recordcount=1000 -p operationcount=1000
```

Captured per run (provenance **REAL_YCSB**, stored in `ycsb_runs.json`): command, status, YCSB/Java versions, wall time, and YCSB's own measured metrics — overall throughput (ops/sec), runtime, READ/UPDATE/INSERT/SCAN/RMW operation counts, average latency, P95, P99. Measured example on this container: Workload A, 1000 ops → ~43,478 ops/s, READ P99 22µs, UPDATE P99 43µs (values vary per run; never hard-coded).

## Honest scope note

The `basic` binding executes YCSB's real workload engine (distributions, operation mixes, client measurement) against a print-only store. Connecting YCSB to a live database binding (MongoDB/Cassandra/JDBC) is a configuration extension, not implemented here. Hotspot forecasting models train on simulator/CSV telemetry; YCSB runs provide real benchmark measurements and are labeled REAL_YCSB everywhere.

## If YCSB is absent (other environments)

Nothing is faked: `/ycsb/validate` reports `ycsb_installed: false`, the UI badge shows **YCSB NOT CONFIGURED · SYNTHETIC MODE**, and `/ycsb/run` returns status `YCSB_NOT_CONFIGURED`. One-time configuration: install Java, extract official YCSB release, set `YCSB_HOME` in `backend/.env`.
