# API Reference

Base: `/api/v1` · Interactive OpenAPI: `/docs`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Service status, sim state, active model, YCSB status |
| GET | `/ycsb/validate` | YCSB/Java availability + supported workloads |
| GET | `/cluster` | Cluster snapshot (nodes, loads, CV, workload) |
| GET | `/telemetry?limit=` | Per-second cluster telemetry history |
| GET | `/telemetry/node/{id}` | Per-node history |
| GET | `/hotspots` | Per-node current + predicted hotspot state |
| GET | `/predictions` | Recent predictions (probability, confidence, severity) |
| GET | `/explain/{node_id}` | Feature-perturbation contributions for active model |
| POST | `/workloads/start` | Start YCSB-compatible/synthetic workload |
| POST | `/workloads/stop` `/workloads/reset` | Control |
| GET | `/workloads/presets` | YCSB presets + distributions |
| POST | `/models/train` | Train gru/lstm/lr/rf/threshold/moving_average |
| GET | `/models` `/models/comparison` | Registry + measured metrics matrix |
| POST | `/models/{name}/activate` | Set active inference model |
| POST | `/decision` | Decision engine (action, reason, cost, benefit, guardrails) |
| POST | `/mitigation/simulate` | Simulated REPLICATE/MIGRATE/CACHE_PROMOTION/THROTTLE + before/after |
| GET | `/mitigations` | Mitigation log |
| POST | `/whatif` | Parameter sweep simulation trace |
| POST | `/experiments/run` | Workload × model grid on identical traces |
| GET | `/experiments` | Experiment log |
| POST | `/demo/start` `/demo/reset` | One-click demo scenario |
| GET | `/audit` | Audit log |
| GET | `/features/schema` | Feature names |
