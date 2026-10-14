# Demo Guide

## One-click demo (recommended)

1. Open the dashboard → **Demo Mode**
2. Click **Start Demo** (or the topbar ⚡ Start Demo)
3. The orchestrator: resets → starts a YCSB-B flash-crowd workload (zipfian skew + periodic burst, seed 42) → trains a small GRU → streams live predictions → explains the top prediction → queries the decision engine → simulates the recommended mitigation → prints before/after P99 and load CV in the log.

## Manual 30-second tour

1. **Overview**: KPIs (nodes, IOPS, P95/P99, load CV), live load/P99 chart, predicted hotspots with probability & severity.
2. **Workload Lab**: pick Workload B, zipfian, `request_rate=900`, burst 3× at t=60 → Run Workload.
3. **Model Training**: train `gru` (defaults) → inspect measured F1/AUC + loss curves.
4. **Hotspot Monitor**: watch predicted probability rise ahead of the burst; click **Cache** or **Replicate** on a hot node.
5. **Mitigation Center**: compare before/after P95/P99/CV; **Recommend** shows the decision engine's choice + guardrails.
6. **Explainability**: select the hot node → perturbation contributions.
7. **Model Comparison / Experiments**: measured side-by-side matrix.

## Reset

Topbar **Reset** or Demo page **Reset** returns to a clean idle state.
