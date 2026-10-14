# Methodology

## Research Question

Can temporal workload and storage telemetry be used to predict an upcoming storage hotspot before saturation and select an appropriate preventive mitigation?

## Base vs Extension

| | KML (Akgun et al.) | Predictive Storage Guardian |
|---|---|---|
| Timing | Reactive (current workload) | Predictive (future hotspot) |
| Action space | Single parameter (readahead, rsize) | Multi-action (replicate/migrate/cache/throttle) |
| Scope | Component-specific | Cross-layer (cache/node/partition/key) |
| Output | Workload class → tuned parameter | Probability + confidence + lead time + explanation + guarded action |
| Mitigation Timing | N/A (single parameter) | **Buffer-aware dynamic transfer feasibility validation** |

## Hotspot Score (simulator-derived ground truth signal)

```
hotspot_score = 0.4*load + 0.3*queue_pressure + 0.2*latency_pressure + 0.1*(1 - cache_hit_rate)
```
Configurable threshold (default 0.6) → severity NORMAL/LOW/MEDIUM/HIGH/CRITICAL.

## Labels

At window `i`: label = 1 if any future window in `(i, i+horizon]` crosses the hotspot threshold. Horizon configurable (5/10/15 min via `horizon_windows`). **No future data is used as model input** — features at `i` only use windows `≤ i`.

## Split

Chronological by window time-index: 70% train / 15% val / 15% test. Training trace uses periodic bursts so all splits contain both classes.

## Metrics (all measured)

Precision, Recall, F1, ROC-AUC, FPR, FNR, confusion matrix, inference latency (batch-of-1, after warmup), training time, loss curves.

## Confidence

Heuristic confidence from probability margin (`|p−0.5|*2`, capped) mapped to LOW/MEDIUM/HIGH with decision guardrails (min confidence 0.55). Documented limitation: not calibrated (Platt/isotonic) — see LIMITATIONS.

## Buffer-Aware Mitigation Feasibility Model

Proactive decisions depend on the relation between **Lead Time** ($T_{\text{lead}}$) and **Mitigation Transfer Duration** ($\tau_{\text{action}}$):

$$\Delta t_{\text{buffer}} = T_{\text{lead}} - \tau_{\text{action}}$$

### 1. Action Duration Models ($\tau_{\text{action}}$)
- **`CACHE_PROMOTION`**: $\tau \approx 1.0\text{s}$ (RAM/SSD metadata tiering).
- **`THROTTLE`**: $\tau \approx 0.2\text{s}$ (token bucket rate limiting).
- **`REPLICATE`**: $\tau_{\text{rep}} = \frac{\text{Partition Size (MB)}}{\text{Network Bandwidth (MB/s)}} \times (1 + 0.8 \times \text{load}_{\text{dest}}) + 2.0\text{s}$.
- **`MIGRATE`**: $\tau_{\text{mig}} = \frac{\text{Partition Size (MB)}}{\text{Network Bandwidth (MB/s)}} \times (1 + 0.6 \times \text{load}_{\text{src}} + 0.6 \times \text{load}_{\text{dest}}) + 4.0\text{s}$.

### 2. Graceful Downgrade Hierarchy (When Buffer Time Exceeds)
If $\Delta t_{\text{buffer}} < \text{Safety Margin}$ (default 15s):
1. Candidate `MIGRATE` $\rightarrow$ downgraded to `REPLICATE` (if read-heavy and $\Delta t_{\text{rep}} \ge 15\text{s}$) or **`CACHE_PROMOTION`** (pins hot keys in $\sim 1\text{s}$).
2. If write-heavy overload $\rightarrow$ downgraded to **`THROTTLE`** to shed peak traffic.
3. If $T_{\text{lead}} < 2\text{s}$ $\rightarrow$ hands off to reactive controller to prevent launching non-viable background transfers.
4. If in-flight migration is active and node breaches $\text{load} \ge 0.96$, the transfer is automatically **preempted** (`abort_mitigation`) to prioritize live client queries.
