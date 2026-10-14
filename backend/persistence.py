"""Disk-persisted model registry: weights + scaler + metadata survive restarts."""
from __future__ import annotations
import json
import pickle
from pathlib import Path
from typing import Dict, List, Optional

import torch

from models_ml import SeqModel

REGISTRY_DIR = Path(__file__).parent / "model_registry"
REGISTRY_DIR.mkdir(exist_ok=True)
META_FILE = REGISTRY_DIR / "registry.json"
ACTIVE_FILE = REGISTRY_DIR / "active_model.txt"


def _safe_name(name: str) -> str:
    return name.replace("/", "_")


def save_model(name: str, entry: Dict, record: Dict) -> None:
    """Persist one model entry: weights (torch/pickle), scaler, metadata."""
    base = REGISTRY_DIR / _safe_name(name)
    kind = entry["kind"]
    if kind in ("gru", "lstm"):
        torch.save({
            "state_dict": entry["model"].state_dict(),
            "input_dim": entry["model"].rnn.input_size,
            "hidden": entry["model"].rnn.hidden_size,
            "layers": entry["model"].rnn.num_layers,
            "kind": kind,
        }, base.with_suffix(".pt"))
    elif kind in ("lr", "rf") and entry.get("clf") is not None:
        with open(base.with_suffix(".pkl"), "wb") as f:
            pickle.dump({"clf": entry["clf"], "scaler": entry["scaler"]}, f)
    # heuristic baselines: persist threshold dict
    if kind in ("threshold", "moving_average"):
        with open(base.with_suffix(".pkl"), "wb") as f:
            pickle.dump({k: v for k, v in entry.items() if k != "scaler"}, f)
    if "scaler" in entry and kind not in ("lr", "rf"):
        with open(REGISTRY_DIR / f"{_safe_name(name)}.scaler.pkl", "wb") as f:
            pickle.dump(entry["scaler"], f)
    # metadata
    meta = _read_meta()
    meta[name] = record
    META_FILE.write_text(json.dumps(meta, indent=1))
    # first-ever saved model becomes active on disk; later saves keep current active
    if not ACTIVE_FILE.exists() or not ACTIVE_FILE.read_text().strip():
        ACTIVE_FILE.write_text(name)


def load_all() -> Dict[str, Dict]:
    """Rebuild in-memory entries from disk. Returns {name: entry_with_record}."""
    out: Dict[str, Dict] = {}
    if not META_FILE.exists():
        return out
    meta = json.loads(META_FILE.read_text())
    for name, record in meta.items():
        kind = record["kind"]
        base = REGISTRY_DIR / _safe_name(name)
        try:
            if kind in ("gru", "lstm"):
                ckpt = torch.load(base.with_suffix(".pt"), map_location="cpu", weights_only=False)
                m = SeqModel(input_dim=ckpt["input_dim"], hidden=ckpt["hidden"],
                             layers=ckpt["layers"], kind=ckpt["kind"])
                m.load_state_dict(ckpt["state_dict"])
                m.eval()
                entry = {"kind": kind, "model": m}
            elif kind in ("lr", "rf"):
                with open(base.with_suffix(".pkl"), "rb") as f:
                    d = pickle.load(f)
                entry = {"kind": kind, "clf": d["clf"], "scaler": d["scaler"], "degenerate": False}
            else:
                with open(base.with_suffix(".pkl"), "rb") as f:
                    entry = pickle.load(f)
            sp = REGISTRY_DIR / f"{_safe_name(name)}.scaler.pkl"
            if sp.exists() and "scaler" not in entry:
                with open(sp, "rb") as f:
                    entry["scaler"] = pickle.load(f)
            entry["record"] = record
            out[name] = entry
        except Exception:
            continue
    return out


def load_active() -> Optional[str]:
    if ACTIVE_FILE.exists():
        v = ACTIVE_FILE.read_text().strip()
        return v or None
    return None


def set_active(name: str) -> None:
    ACTIVE_FILE.write_text(name)


def _read_meta() -> Dict:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text())
        except Exception:
            return {}
    return {}
