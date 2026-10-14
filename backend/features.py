"""Feature engineering + hotspot labels."""
from __future__ import annotations
from collections import deque
from typing import Deque, Dict, List, Tuple
import numpy as np


FEATURE_NAMES = [
    "request_rate", "request_growth", "read_ratio", "write_ratio",
    "queue_depth", "queue_growth",
    "avg_latency", "latency_growth", "p95_latency", "p99_latency",
    "throughput", "cpu", "memory", "cache_hit_rate",
    "node_utilization", "load_imbalance", "hotspot_score",
]


def aggregate_window(telemetry_seconds: List[Dict]) -> Dict:
    """Aggregate 60x per-second telemetry rows into a single windowed dict per node."""
    if not telemetry_seconds:
        return {}
    keys = telemetry_seconds[0].keys()
    agg = {}
    for k in ["read_iops", "write_iops", "throughput_mbps"]:
        agg[k] = float(np.mean([t[k] for t in telemetry_seconds]))
    for k in ["cpu", "memory", "storage", "cache_hit_rate", "load", "hotspot_score"]:
        agg[k] = float(np.mean([t[k] for t in telemetry_seconds]))
    for k in ["queue_depth", "avg_latency_ms"]:
        agg[k] = float(np.mean([t[k] for t in telemetry_seconds]))
    agg["p95_latency_ms"] = float(np.percentile([t["p95_latency_ms"] for t in telemetry_seconds], 95))
    agg["p99_latency_ms"] = float(np.percentile([t["p99_latency_ms"] for t in telemetry_seconds], 99))
    agg["t"] = telemetry_seconds[-1]["t"]
    agg["node_id"] = telemetry_seconds[0]["node_id"]
    return agg


def build_feature_vector(window: Dict, prev_window: Dict, cluster_loads: List[float]) -> List[float]:
    """Given the current window & prev, return a fixed-length feature vector."""
    reads = window["read_iops"]
    writes = window["write_iops"]
    total = max(1e-6, reads + writes)
    prev_total = max(1e-6, prev_window.get("read_iops", 0) + prev_window.get("write_iops", 0)) if prev_window else total
    read_ratio = reads / total
    write_ratio = writes / total
    req_growth = (total - prev_total) / prev_total if prev_total else 0.0
    q = window["queue_depth"]
    q_prev = prev_window.get("queue_depth", q) if prev_window else q
    q_growth = q - q_prev
    lat = window["avg_latency_ms"]
    lat_prev = prev_window.get("avg_latency_ms", lat) if prev_window else lat
    lat_growth = lat - lat_prev
    node_util = max(window["cpu"], window["memory"], window["load"])
    cluster_mean = float(np.mean(cluster_loads)) if cluster_loads else 0.5
    imbalance = abs(window["load"] - cluster_mean)
    return [
        total, req_growth, read_ratio, write_ratio,
        q, q_growth,
        lat, lat_growth, window["p95_latency_ms"], window["p99_latency_ms"],
        window["throughput_mbps"], window["cpu"], window["memory"], window["cache_hit_rate"],
        node_util, imbalance, window["hotspot_score"],
    ]


class FeaturePipeline:
    """Rolls per-second telemetry into 60-sec windows and produces sequences."""

    def __init__(self, window_size: int = 60, seq_len: int = 10):
        self.window_size = window_size
        self.seq_len = seq_len
        self.buffers: Dict[str, Deque[Dict]] = {}
        self.windows: Dict[str, List[Dict]] = {}
        self.features: Dict[str, List[List[float]]] = {}

    def add_second(self, telemetry_by_node: Dict[str, Dict]):
        for nid, row in telemetry_by_node.items():
            buf = self.buffers.setdefault(nid, deque(maxlen=self.window_size))
            buf.append(row)
            if len(buf) == self.window_size:
                w = aggregate_window(list(buf))
                self.windows.setdefault(nid, []).append(w)
                buf.clear()

    def build_features(self):
        # Cluster-wide mean load per window index
        node_ids = list(self.windows.keys())
        if not node_ids:
            return
        min_len = min(len(self.windows[n]) for n in node_ids)
        for nid in node_ids:
            self.features.setdefault(nid, [])
            for i in range(min_len):
                prev = self.windows[nid][i - 1] if i > 0 else {}
                cluster_loads = [self.windows[n][i]["load"] for n in node_ids]
                fv = build_feature_vector(self.windows[nid][i], prev, cluster_loads)
                self.features[nid].append(fv)

    def sequences_with_labels(self, horizon_windows: int = 5, hotspot_threshold: float = 0.65):
        """Return (X, y, node_ids_seq, t_index). y is 1 if any future window in
        [i+1 .. i+horizon] has hotspot_score >= threshold for that same node."""
        Xs, ys, meta = [], [], []
        for nid, feats in self.features.items():
            windows = self.windows[nid]
            for i in range(self.seq_len, len(feats) - horizon_windows):
                seq = feats[i - self.seq_len:i]
                future_scores = [windows[j]["hotspot_score"] for j in range(i, i + horizon_windows)]
                y = 1 if max(future_scores) >= hotspot_threshold else 0
                Xs.append(seq)
                ys.append(y)
                meta.append({"node_id": nid, "t_index": i,
                             "future_hotspot_score": max(future_scores)})
        return np.array(Xs, dtype=np.float32), np.array(ys, dtype=np.int64), meta
