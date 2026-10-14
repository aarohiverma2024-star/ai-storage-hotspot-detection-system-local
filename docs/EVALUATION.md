# Evaluation

## Detection metrics (measured on held-out chronological test split)

Precision, Recall, F1, ROC-AUC, FPR, FNR, confusion matrix.

## Operational metrics (measured from simulator)

P95/P99 latency, queue depth, throughput, load CV, hotspot duration, intervention count/cost — captured **before vs after** every simulated mitigation (`/api/v1/mitigation/simulate` response and Mitigation Center UI).

## Inference metrics

Batch-of-1 inference latency measured per trained model (after one warmup call). GRU ≈ 4–17 ms, LSTM ≈ 0.7–6 ms, classical ≪ 1 ms on this container's CPU.

## Reactive vs Predictive

- Reactive baselines: Static Threshold, Moving Average (trigger on *current* window crossing).
- Predictive: GRU/LSTM trigger on *forecast* probability with horizon 5–15 min.
- Compare via **Experiment Runner** (`/experiments`) across workloads and models on identical traces; mitigation before/after tables show system-level deltas.

## Experiment protocol

1. Choose workloads (A–F) and models.
2. Same seed, same trace per (workload, model) cell.
3. Metrics recorded per cell with config; stored in `experiments` log.

## Label honesty

All numbers on the dashboard are either **Measured** (model metrics, before/after) or **Simulated** (telemetry). Unmeasured items display "—" or "Not Evaluated".
