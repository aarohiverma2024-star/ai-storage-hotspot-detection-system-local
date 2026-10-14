# Architecture

## 1. Components

| Layer | File | Responsibility |
|---|---|---|
| Simulator | `backend/simulator.py` | Deterministic distributed storage cluster sim; YCSB-compatible workload generator (A–F), in-flight progressive data migration tracking, load tax, preemption |
| Features | `backend/features.py` | 1s telemetry → 60s windows → temporal feature vectors → sequences + future-based labels |
| Models | `backend/models_ml.py` | Threshold, Moving-Average, LR, RF (sklearn), GRU, LSTM (PyTorch); chronological split; metrics |
| Decision Engine | `backend/decision.py` | Dual-timeframe buffer validation, dynamic action duration modeling, Graceful Downgrade Policy, guardrails |
| State/Loop | `backend/state.py` | Background simulator thread (accelerated clock), live inference, prediction log, audit |
| API | `backend/routers.py` | REST `/api/v1/*` with buffer telemetry and simulation endpoints |
| Frontend | `frontend/src/pages/*` | Interactive dashboard (React + Tailwind + Recharts) with live buffer status visualization |

---

## 2. Reframed Architecture: Dual-Timeframe Closed Loop

Unlike naive reactive systems or linear predictive pipelines, this architecture explicitly separates actions into **Slow / Proactive** and **Fast / Sub-second** layers, governed by a **Buffer Feasibility Check**:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                                 OBSERVE & FORECAST                                     │
│  1s Storage Telemetry ──► 60s Feature Windows ──► ML Inference (GRU / LSTM)           │
│                                                     │                                  │
│                                                     ▼                                  │
│                                          Predicted Hotspot:                            │
│                                       (Probability, Lead Time T_lead)                  │
└─────────────────────────────────────────────┬──────────────────────────────────────────┘
                                              │
                                              ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        BUFFER FEASIBILITY & DOWNSCALING ENGINE                         │
│                                                                                        │
│  Candidate Action Selection (MIGRATE / REPLICATE / CACHE_PROMOTION / THROTTLE)         │
│  Dynamic Transfer Duration Model: τ_action = (Size / Bandwidth) * Load_Factor + Handshake │
│  Buffer Safety Window: Δt_buffer = T_lead - τ_action                                  │
│                                                                                        │
│                Does Δt_buffer ≥ Safety Margin (e.g. 15s)?                              │
│                         /                      \                                       │
│                       YES                       NO (Buffer Exceeded)                   │
│                        │                         │                                     │
│                        ▼                         ▼                                     │
│               [PATH A: HEAVY ACTION]   [PATH B: GRACEFUL DOWNGRADE]                    │
│               - Partition Migration    - Downgrade to Sub-second Action:               │
│               - Peer Replication         • CACHE_PROMOTION (RAM/SSD pin: ~1s)          │
│               - In-flight tracking       • THROTTLE (Rate limit: ~0.2s)                │
│                 with I/O transfer tax  - Prevents fatal I/O transfer storms            │
└────────────────────────┬─────────────────────────┬─────────────────────────────────────┘
                         │                         │
                         ▼                         ▼
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                             EXECUTE, MEASURE & AUDIT                                   │
│  Simulated Storage Engine ──► Before / After Metric Diff ──► Feedback & ML Audit Log   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. What Happens If the Buffer Time Exceeds?

A critical failure mode in predictive systems is the **Mitigation Race Condition**:
If a partition migration requires $\tau = 60\text{s}$, but the predicted hotspot arrives in $T_{\text{lead}} = 20\text{s}$, initiating migration will cause a **destructive I/O storm**—the node will suffer both peak client queries and background disk copying simultaneously.

### The System's Four-Stage Defense:

1. **Pre-Execution Feasibility Evaluation**:
   Before dispatching any heavy command, `choose_action()` verifies:
   $$\Delta t_{\text{buffer}} = T_{\text{lead}} - \tau_{\text{action}} \ge \text{Safety Margin}$$
2. **Graceful Action Downgrade**:
   If $\Delta t_{\text{buffer}} < \text{Safety Margin}$, the system **refuses to launch the heavy transfer**. Instead, it downscales to a zero-transfer fast mitigation:
   - Read-heavy workloads: Downgraded to **`CACHE_PROMOTION`** (pins hot keys in memory within $\sim 1\text{s}$).
   - Write-heavy or extreme load: Downgraded to **`THROTTLE`** (immediate token bucket rate limiting in $\sim 0.2\text{s}$).
3. **Mid-Transfer Preemption (Circuit Breaker)**:
   If a migration was launched and an unexpected flash crowd causes node load to cross critical saturation ($\text{load} \ge 0.96$), the simulator triggers `abort_mitigation()`, pausing background transfer to give 100% bandwidth back to client I/O.
4. **Audit & Closed-Loop Logging**:
   The event is marked as `EXCEEDED_DOWNGRADED` with before/after measurements preserved in `/mitigations` to provide feedback for retraining prediction horizons.

---

## 4. Real-time Simulation & Transport

- **Clock**: Accelerated simulation clock (20 sim-seconds per wall-second).
- **Transport**: REST polling every 2.5–3s.
- **In-flight Tracking**: `ClusterSimulator` simulates duration, transient transfer penalties, and completion callbacks for multi-second transfers.
