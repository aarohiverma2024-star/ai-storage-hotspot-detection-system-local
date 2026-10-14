# Dataset

## Sources

| Source | Status | Label |
|---|---|---|
| YCSB CLI (official 0.17.0) | **Configured** (`/opt/ycsb`, Java 17) | `REAL_YCSB` |
| Embedded YCSB-compatible generator | Active (fallback / simulator driver) | `Simulated` |
| CSV telemetry import | **Implemented** (`POST /api/v1/datasets/upload` → training pipeline) | `IMPORTED_CSV` |

The embedded generator reproduces YCSB workload *behavior*: workloads A–F operation mixes, uniform/zipfian/latest/hotkey/hotspot distributions, record/operation counts, request rate, seed, bursts.

## Telemetry Schema (per second, per node) — all simulator-derived

`node_id, t, read_iops, write_iops, throughput_mbps, cpu, memory, storage, queue_depth, avg_latency_ms, p95_latency_ms, p99_latency_ms, cache_hit_rate, load, hotspot_score, tier, replicas_hosted, throttle_pct`

## Features (17, per 60s window)

request_rate, request_growth, read_ratio, write_ratio, queue_depth, queue_growth, avg_latency, latency_growth, p95_latency, p99_latency, throughput, cpu, memory, cache_hit_rate, node_utilization, load_imbalance, hotspot_score

## Normalization

`StandardScaler` fit **on training data only** (per feature across time steps), stored inside the model entry and applied at inference. LR/RF use their own internal scaler.

## Sequences

Default: 10 windows × 60s ≈ 10 minutes of history. Configurable 5/10/20.

## Labels

Future-observation-based: hotspot within next `horizon_windows` (default 5 ≈ 5 min). Leakage-free: inputs never include future windows.
