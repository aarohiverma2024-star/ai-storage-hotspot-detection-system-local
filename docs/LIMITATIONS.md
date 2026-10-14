# Limitations

1. **Simulator-only storage**: no production storage backend is connected; all mitigations are simulated. YCSB runs use the official CLI with the `basic` (print-only) binding — real YCSB workload engine and measurements, no live database binding.
2. **Confidence is heuristic** (probability margin), not calibrated (Platt/isotonic calibration is future work).
3. **Lead time** is a research target (5/10/15 min horizon); actual lead time depends on trace and is measured experimentally, not guaranteed.
4. **Real-time transport**: REST polling (2.5–3s) with accelerated sim clock; WebSocket/SSE streaming is a P1 enhancement.
5. **Model persistence**: implemented on disk (`backend/model_registry/` — weights `.pt`/`.pkl`, scalers, `registry.json`, active model pointer). Survives backend restarts. MongoDB mirroring is optional P1.
6. **Auth**: JWT roles (Viewer/Operator/Admin) specified but deferred; current build is single-operator.
7. **CSV datasets**: uploaded telemetry CSVs are validated (15 required columns, ≥120 rows), stored in `backend/uploads/`, and genuinely consumed by the training pipeline. Generalization of models across very different CSV distributions is the user's experimental responsibility.
8. **Small training sets**: default 3600s traces yield ~180 sequences; larger traces recommended for stronger neural results.
9. **Browser extension**: optional component, not built.
10. **LR/RF perfect scores** on default synthetic traces indicate high separability of the simulator, not production-grade performance.
