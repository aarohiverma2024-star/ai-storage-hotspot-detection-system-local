"""Integration tests: workload → telemetry → features → models → decision → mitigation."""
import numpy as np
import pytest

from simulator import ClusterSimulator, WorkloadConfig, YCSB_PRESETS
from features import FeaturePipeline, FEATURE_NAMES
from models_ml import (
    SeqModel, train_seq, eval_binary, train_threshold_baseline, predict_threshold,
    train_ma_baseline, predict_ma, train_classical, predict_classical, predict_seq,
)
from decision import choose_action
from sklearn.preprocessing import StandardScaler


def _trace(seed=42, seconds=1500):
    sim = ClusterSimulator(num_nodes=4, seed=seed)
    cfg = WorkloadConfig(workload="B", seed=seed, request_rate=1000.0,
                         hot_key_traffic_share=0.55, burst_multiplier=3.0,
                         burst_start=240, burst_duration=150, burst_period=600)
    sim.set_workload(cfg)
    fp = FeaturePipeline(window_size=60, seq_len=10)
    for _ in range(seconds):
        fp.add_second(sim.step())
    fp.build_features()
    return fp, sim


def test_workload_and_telemetry():
    fp, sim = _trace(seconds=300)
    assert sim.t_sec == 300
    snap = sim.snapshot()
    assert len(snap["nodes"]) == 4
    assert all("hotspot_score" in n for n in snap["nodes"])


def test_determinism():
    _, s1 = _trace(seed=7, seconds=120)
    _, s2 = _trace(seed=7, seconds=120)
    assert s1.snapshot()["nodes"] == s2.snapshot()["nodes"]


def test_features_and_labels_no_leakage():
    fp, _ = _trace()
    X, y, meta = fp.sequences_with_labels(horizon_windows=5, hotspot_threshold=0.6)
    assert X.shape[-1] == len(FEATURE_NAMES)
    assert len(X) == len(y) == len(meta)
    assert 0 < y.sum() < len(y)  # both classes present
    # labels come only from future windows; inputs end at t_index-1
    for m in meta[:10]:
        assert m["t_index"] >= fp.seq_len


def test_all_models_train_and_predict():
    fp, _ = _trace()
    X, y, meta = fp.sequences_with_labels(horizon_windows=5, hotspot_threshold=0.6)
    t_idx = np.array([m["t_index"] for m in meta])
    tmax = t_idx.max()
    tr = t_idx < int(tmax * 0.7); te = t_idx >= int(tmax * 0.85)
    Xtr, ytr, Xte, yte = X[tr], y[tr], X[te], y[te]
    sc = StandardScaler().fit(Xtr.reshape(-1, X.shape[-1]))
    scale = lambda a: sc.transform(a.reshape(-1, X.shape[-1])).reshape(a.shape)
    Xtr_s, Xte_s = scale(Xtr), scale(Xte)

    th = train_threshold_baseline(Xtr_s, ytr)
    assert len(predict_threshold(th, Xte_s)) == len(yte)
    ma = train_ma_baseline(Xtr_s, ytr)
    assert len(predict_ma(ma, Xte_s)) == len(yte)
    lr = train_classical(Xtr, ytr, kind="lr")
    m = eval_binary(yte, predict_classical(lr, Xte))
    assert 0.0 <= m["f1"] <= 1.0
    gru = SeqModel(input_dim=X.shape[-1], hidden=16, kind="gru")
    train_seq(gru, Xtr_s, ytr, Xte_s[:20], yte[:20], epochs=3)
    p = predict_seq(gru, Xte_s)
    assert p.min() >= 0 and p.max() <= 1
    lstm = SeqModel(input_dim=X.shape[-1], hidden=16, kind="lstm")
    train_seq(lstm, Xtr_s, ytr, Xte_s[:20], yte[:20], epochs=3)
    assert len(predict_seq(lstm, Xte_s)) == len(yte)


def test_decision_engine_guardrails():
    low = choose_action({"probability": 0.9, "confidence": 0.3, "lead_time_sec": 300})
    assert low["action"] == "MONITOR" and low["guardrail_passed"] is False
    high = choose_action({"probability": 0.9, "confidence": 0.9, "lead_time_sec": 300,
                          "read_ratio": 0.95, "cache_hit_rate": 0.5,
                          "access_concentration": 0.6, "node_load": 0.6,
                          "cluster_headroom": 0.3})
    assert high["action"] == "CACHE_PROMOTION"


def test_mitigations_change_state():
    _, sim = _trace(seconds=200)
    r = sim.replicate(0)
    assert r["ok"] and len(r["replicas"]) == 2
    m = sim.migrate(1)
    assert m["ok"] and m["from"] != m["to"]
    c = sim.promote_cache(2)
    assert c["ok"]
    t = sim.throttle("node-01", 0.5)
    assert t["ok"] and t["throttle_pct"] == 0.5
