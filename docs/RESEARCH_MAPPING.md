# Research Mapping

| BASE PAPER (KML, Akgun et al.) | LIMITATION / OPPORTUNITY | OUR EXTENSION | EVALUATION |
|---|---|---|---|
| Observe-and-tune: ML classifies current workload | Reactive — acts only after the workload is present | GRU/LSTM forecast of future hotspot probability + confidence + lead time | Detection metrics (P/R/F1/AUC) + measured lead time on held-out future data |
| Readahead / NFS rsize tuning | Single-parameter intervention | Multi-action mitigation: replicate / migrate / cache-promote / throttle | Before/after P95, P99, load CV, queue depth per simulated action |
| Component-specific optimization | Limited cross-layer coordination | Unified hotspot signal across cache/node/partition/key layers | Layer-aware decision engine + per-layer action routing |
| ML workload understanding | No prediction explanation or trust signal | Perturbation-based feature attribution + confidence tiers + guardrails | Explainability view; guardrail-gated decisions; audit log |

## Positioning

Base question: *"What should the storage system tune based on the current workload?"*
Our question: *"What storage hotspot is likely to happen next, why is it likely, and what preventive action should be taken before it becomes critical?"*

We do **not** claim to improve KML's CPU/memory overhead, nor that the base paper contains forecasting, our decision engine, or our mitigation strategies.
