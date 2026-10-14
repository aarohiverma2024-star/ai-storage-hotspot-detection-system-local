"""ML models: Threshold, MovingAvg, LR/RF, GRU, LSTM. Real PyTorch + sklearn."""
from __future__ import annotations
import time
import numpy as np
from typing import Dict, List, Optional, Tuple

import torch
import torch.nn as nn
from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler


DEVICE = torch.device("cpu")


def chronological_split(X: np.ndarray, y: np.ndarray, train=0.7, val=0.15):
    n = len(X)
    a = int(n * train)
    b = int(n * (train + val))
    return (X[:a], y[:a]), (X[a:b], y[a:b]), (X[b:], y[b:])


class SeqModel(nn.Module):
    def __init__(self, input_dim: int, hidden: int = 32, layers: int = 1, dropout: float = 0.15,
                 kind: str = "gru"):
        super().__init__()
        self.kind = kind
        rnn_cls = nn.GRU if kind == "gru" else nn.LSTM
        self.rnn = rnn_cls(input_dim, hidden, num_layers=layers, batch_first=True,
                           dropout=dropout if layers > 1 else 0.0)
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(hidden, 1)

    def forward(self, x):
        out, _ = self.rnn(x)
        h = out[:, -1, :]
        return torch.sigmoid(self.head(self.dropout(h))).squeeze(-1)


def train_seq(model: SeqModel, X_tr, y_tr, X_val, y_val, lr=1e-3, epochs=15, batch=64,
              on_epoch=None) -> Dict:
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.BCELoss()
    Xtr_t = torch.tensor(X_tr, dtype=torch.float32)
    ytr_t = torch.tensor(y_tr, dtype=torch.float32)
    Xv_t = torch.tensor(X_val, dtype=torch.float32)
    yv_t = torch.tensor(y_val, dtype=torch.float32)
    n = len(Xtr_t)
    history = []
    best_val = float("inf")
    best_state = None
    patience, bad = 3, 0
    for epoch in range(epochs):
        model.train()
        idx = np.arange(n)
        np.random.shuffle(idx)
        losses = []
        for i in range(0, n, batch):
            b = idx[i:i + batch]
            xb = Xtr_t[b]
            yb = ytr_t[b]
            opt.zero_grad()
            p = model(xb)
            loss = loss_fn(p, yb)
            loss.backward()
            opt.step()
            losses.append(float(loss.item()))
        tr_loss = float(np.mean(losses)) if losses else 0.0
        model.eval()
        with torch.no_grad():
            vp = model(Xv_t) if len(Xv_t) else torch.tensor([0.0])
            v_loss = float(loss_fn(vp, yv_t).item()) if len(Xv_t) else 0.0
        history.append({"epoch": epoch + 1, "train_loss": round(tr_loss, 5),
                        "val_loss": round(v_loss, 5)})
        if on_epoch:
            on_epoch(history[-1])
        if v_loss < best_val - 1e-4:
            best_val = v_loss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            bad = 0
        else:
            bad += 1
            if bad >= patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    return {"history": history, "best_val_loss": best_val}


def eval_binary(y_true, y_pred_prob, thresh=0.5) -> Dict:
    from sklearn.metrics import roc_auc_score
    y_true = np.asarray(y_true).astype(int)
    y_prob = np.asarray(y_pred_prob).astype(float)
    y_pred = (y_prob >= thresh).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    prec = tp / max(1, tp + fp)
    rec = tp / max(1, tp + fn)
    f1 = 2 * prec * rec / max(1e-9, prec + rec)
    fpr = fp / max(1, fp + tn)
    fnr = fn / max(1, fn + tp)
    try:
        auc = float(roc_auc_score(y_true, y_prob))
    except Exception:
        auc = 0.0
    return {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
            "auc": round(auc, 4), "fpr": round(fpr, 4), "fnr": round(fnr, 4),
            "confusion": {"tp": tp, "fp": fp, "tn": tn, "fn": fn}}


class ModelRegistry:
    def __init__(self):
        self.models: Dict[str, Dict] = {}

    def register(self, name: str, entry: Dict):
        self.models[name] = entry

    def get(self, name: str) -> Optional[Dict]:
        return self.models.get(name)

    def list(self) -> List[str]:
        return list(self.models.keys())


def train_threshold_baseline(X_seq: np.ndarray, y: np.ndarray, feature_index: int = 4) -> Dict:
    """Static threshold on last-step queue_depth feature (index 4)."""
    last = X_seq[:, -1, feature_index]
    # Pick threshold at 75th percentile of positives if any, else 75th overall
    if (y == 1).sum() >= 2:
        thresh = float(np.percentile(last[y == 1], 20))
    else:
        thresh = float(np.percentile(last, 75))
    return {"kind": "threshold", "feature_index": feature_index, "threshold": thresh}


def predict_threshold(model: Dict, X_seq: np.ndarray) -> np.ndarray:
    last = X_seq[:, -1, model["feature_index"]]
    prob = 1 / (1 + np.exp(-(last - model["threshold"])))
    return prob


def train_ma_baseline(X_seq: np.ndarray, y: np.ndarray, feature_index: int = 4) -> Dict:
    # Moving average of the feature across the sequence, threshold at 60th percentile
    ma = X_seq[:, :, feature_index].mean(axis=1)
    thresh = float(np.percentile(ma, 60))
    return {"kind": "moving_average", "feature_index": feature_index, "threshold": thresh}


def predict_ma(model: Dict, X_seq: np.ndarray) -> np.ndarray:
    ma = X_seq[:, :, model["feature_index"]].mean(axis=1)
    return 1 / (1 + np.exp(-(ma - model["threshold"])))


def train_classical(X_seq: np.ndarray, y: np.ndarray, kind: str = "rf") -> Dict:
    """Flatten sequence & standardize."""
    X = X_seq.reshape(len(X_seq), -1)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    if kind == "lr":
        clf = LogisticRegression(max_iter=500)
    else:
        clf = RandomForestClassifier(n_estimators=80, random_state=42, n_jobs=1)
    if len(np.unique(y)) < 2:
        return {"kind": kind, "scaler": scaler, "clf": None, "degenerate": True}
    clf.fit(Xs, y)
    return {"kind": kind, "scaler": scaler, "clf": clf, "degenerate": False}


def predict_classical(model: Dict, X_seq: np.ndarray) -> np.ndarray:
    X = X_seq.reshape(len(X_seq), -1)
    Xs = model["scaler"].transform(X)
    if model.get("degenerate") or model["clf"] is None:
        return np.zeros(len(Xs))
    return model["clf"].predict_proba(Xs)[:, 1]


def predict_seq(model: SeqModel, X_seq: np.ndarray) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        p = model(torch.tensor(X_seq, dtype=torch.float32))
    return p.numpy()


def perturbation_importance(model, predictor, X_seq: np.ndarray, feature_names: List[str],
                            baseline_prob: Optional[float] = None) -> List[Dict]:
    """Simple feature-perturbation explanation for last-step of sequence."""
    if baseline_prob is None:
        baseline_prob = float(predictor(model, X_seq)[0])
    contribs = []
    for f_idx, fname in enumerate(feature_names):
        X_pert = X_seq.copy()
        # Zero out the feature across the whole sequence
        X_pert[:, :, f_idx] = 0.0
        p_new = float(predictor(model, X_pert)[0])
        contrib = baseline_prob - p_new
        contribs.append({"feature": fname, "contribution": round(contrib, 4),
                         "value": round(float(X_seq[0, -1, f_idx]), 4)})
    contribs.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return contribs
