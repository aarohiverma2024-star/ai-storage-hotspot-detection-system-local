"""Global in-memory state + background simulator loop."""
from __future__ import annotations
import asyncio
import threading
import time
import uuid
import numpy as np
from collections import deque
from typing import Deque, Dict, List, Optional

from simulator import ClusterSimulator, WorkloadConfig
from features import FeaturePipeline, FEATURE_NAMES, build_feature_vector, aggregate_window
from models_ml import (
    SeqModel, train_seq, chronological_split, eval_binary,
    train_threshold_baseline, predict_threshold,
    train_ma_baseline, predict_ma,
    train_classical, predict_classical,
    predict_seq, perturbation_importance,
)
from decision import choose_action, confidence_level, severity_from_score
import torch


class AppState:
    def __init__(self):
        self.sim = ClusterSimulator(num_nodes=4, seed=42)
        self.workload: Optional[WorkloadConfig] = None
        self.pipeline = FeaturePipeline(window_size=60, seq_len=10)
        # per-second telemetry ring
        self.telemetry_history: Deque[Dict] = deque(maxlen=600)  # 10 min
        # aggregated window history
        self.window_history: Dict[str, List[Dict]] = {}
        self.running = False
        self.step_thread: Optional[threading.Thread] = None
        # models: {name: {kind, ...}}
        self.models: Dict[str, Dict] = {}
        self.active_model: Optional[str] = None
        # predictions per node
        self.recent_predictions: List[Dict] = []
        # mitigations log
        self.mitigations: List[Dict] = []
        # experiments
        self.experiments: List[Dict] = []
        # training jobs
        self.training_jobs: Dict[str, Dict] = {}
        # audit
        self.audit: List[Dict] = []
        # config
        self.speed_multiplier = 20  # 20 sim seconds per wall second
        # cached last-known cluster load list
        self.cluster_loads_history: List[List[float]] = []
        self.lock = threading.Lock()

    # -------- Simulator loop --------
    def start(self, workload: WorkloadConfig, num_nodes: Optional[int] = None):
        with self.lock:
            if self.running:
                self.stop()
            if num_nodes is not None:
                self.sim = ClusterSimulator(num_nodes=num_nodes, seed=workload.seed)
            else:
                self.sim = ClusterSimulator(num_nodes=self.sim.num_nodes, seed=workload.seed)
            self.pipeline = FeaturePipeline(window_size=60, seq_len=10)
            self.telemetry_history.clear()
            self.window_history.clear()
            self.recent_predictions.clear()
            self.sim.set_workload(workload)
            self.workload = workload
            self.running = True
            self.step_thread = threading.Thread(target=self._loop, daemon=True)
            self.step_thread.start()

    def stop(self):
        self.running = False
        if self.step_thread and self.step_thread.is_alive():
            self.step_thread.join(timeout=2)
        self.step_thread = None

    def reset(self):
        self.stop()
        self.__init__()

    def _loop(self):
        while self.running:
            for _ in range(self.speed_multiplier):
                if not self.running:
                    return
                telem = self.sim.step()
                snapshot = {"t": self.sim.t_sec - 1,
                            "nodes": telem,
                            "cluster_load_mean": float(np.mean([n["load"] for n in telem.values()])),
                            "cluster_load_cv": float(np.std([n["load"] for n in telem.values()]) /
                                                       max(1e-6, np.mean([n["load"] for n in telem.values()]))),
                            }
                self.telemetry_history.append(snapshot)
                self.pipeline.add_second(telem)
                # Every 60s -> a new window arrives, run inference
                if all(len(self.pipeline.buffers.get(nid, [])) == 0 for nid in self.sim.nodes) and \
                        len(self.pipeline.windows) > 0:
                    self._on_window_complete()
            time.sleep(1.0)

    def _on_window_complete(self):
        node_ids = list(self.pipeline.windows.keys())
        if not node_ids or self.active_model is None:
            return
        entry = self.models.get(self.active_model)
        if not entry:
            return
        # Compute features
        self.pipeline.build_features()
        min_len = min(len(self.pipeline.features[n]) for n in node_ids)
        if min_len < self.pipeline.seq_len:
            return
        for nid in node_ids:
            seq = self.pipeline.features[nid][-self.pipeline.seq_len:]
            X = np.array([seq], dtype=np.float32)
            prob = float(self._infer(entry, X)[0])
            self._record_prediction(nid, prob, entry)

    def _infer(self, entry: Dict, X_seq: np.ndarray):
        kind = entry["kind"]
        if kind in ("threshold", "moving_average", "gru", "lstm") and "scaler" in entry:
            F = X_seq.shape[-1]
            X_seq = entry["scaler"].transform(X_seq.reshape(-1, F)).reshape(X_seq.shape)
        if kind == "threshold":
            return predict_threshold(entry, X_seq)
        if kind == "moving_average":
            return predict_ma(entry, X_seq)
        if kind in ("lr", "rf"):
            return predict_classical(entry, X_seq)
        if kind in ("gru", "lstm"):
            return predict_seq(entry["model"], X_seq)
        return np.zeros(len(X_seq))

    def _record_prediction(self, nid: str, prob: float, entry: Dict):
        # confidence heuristic: |prob - 0.5| * 2 + margin from calibration
        conf = float(min(1.0, abs(prob - 0.5) * 2 + 0.1))
        pred = {
            "prediction_id": str(uuid.uuid4()),
            "timestamp": time.time(),
            "t_sim": self.sim.t_sec,
            "node_id": nid,
            "hotspot_probability": round(prob, 4),
            "confidence": round(conf, 4),
            "confidence_level": confidence_level(conf),
            "severity": severity_from_score(prob),
            "prediction_horizon_sec": 300,
            "model_name": self.active_model,
            "model_kind": entry["kind"],
        }
        self.recent_predictions.append(pred)
        # keep last 200
        if len(self.recent_predictions) > 200:
            self.recent_predictions = self.recent_predictions[-200:]

    # -------- helpers --------
    def latest_telemetry(self) -> Optional[Dict]:
        return self.telemetry_history[-1] if self.telemetry_history else None

    def cluster_snapshot(self) -> Dict:
        latest = self.latest_telemetry() or {"nodes": {}}
        nodes = list(latest.get("nodes", {}).values())
        healthy = sum(1 for n in nodes if n["hotspot_score"] < 0.55)
        at_risk = len(nodes) - healthy
        return {
            "t_sim": self.sim.t_sec, "running": self.running,
            "num_nodes": len(self.sim.nodes),
            "healthy": healthy, "at_risk": at_risk,
            "nodes": nodes,
            "cluster_load_cv": latest.get("cluster_load_cv", 0.0),
            "cluster_load_mean": latest.get("cluster_load_mean", 0.0),
            "workload": self.workload.__dict__ if self.workload else None,
        }


STATE = AppState()

# Restore persisted model registry (weights + scalers + metadata) across restarts
try:
    import persistence
    _restored = persistence.load_all()
    STATE.models.update(_restored)
    _active = persistence.load_active()
    if _active in STATE.models:
        STATE.active_model = _active
    elif STATE.models:
        STATE.active_model = next(iter(STATE.models))
except Exception as _e:
    pass
