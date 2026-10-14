# ML Models

## Models

| Model | Kind | Role |
|---|---|---|
| GRU | PyTorch sequence (GRU → Dropout → Dense → Sigmoid) | **Primary** |
| LSTM | PyTorch sequence | Neural comparison |
| Logistic Regression | sklearn, flattened sequence | Classical baseline |
| Random Forest | sklearn | Classical baseline |
| Static Threshold | last-window queue feature threshold | Reactive baseline |
| Moving Average | rolling-mean threshold (KML-style heuristic) | Reactive baseline |

All models train on the **same processed trace, same features, same chronological split, same horizon**.

## GRU/LSTM training

Adam, BCE loss, early stopping (patience 3, best-val checkpoint restore), validation monitoring per epoch (loss curve exposed to UI). Hyperparameters configurable: hidden, layers, dropout, lr, batch, epochs, seq_len, horizon, hotspot threshold.

## Explainability

Lightweight **feature perturbation**: each of the 17 features is zeroed across the input sequence and the probability delta is reported as its contribution. No SHAP dependency; no invented percentages.

## Versioning

Model registry in-process: name (`<kind>-<id>`), config, metrics, history, scaler, feature schema, inference latency. Activate via `POST /api/v1/models/{name}/activate`.

## Measured example (seed 42, YCSB-B synthetic trace, 3600s, horizon 5×60s)

Measured during CI verification on this build — GRU F1 0.81 / AUC 0.82, LSTM F1 0.82 / AUC 0.85, LR & RF F1 1.0 (synthetic trace highly separable), MA F1 0.77, Threshold F1 0.76. Values vary with seed/config — always trust your own experiment runs, not these numbers.
