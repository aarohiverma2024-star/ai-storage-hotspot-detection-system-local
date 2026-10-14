"""Tests for YCSB detection, CSV ingestion, and model persistence."""
import pickle
import numpy as np
import pytest

import ycsb_runner
import datasets
import persistence


def test_ycsb_detect_real():
    det = ycsb_runner.detect()
    assert det["java_installed"] is True
    assert det["ycsb_installed"] is True
    assert det["ycsb_version"] == "0.17.0"


def test_ycsb_run_real():
    r = ycsb_runner.run_ycsb("A", record_count=200, operation_count=200, threads=1, timeout=120)
    assert r["ok"] is True
    assert r["provenance"] == "REAL_YCSB"
    assert r["status"] == "SUCCESS"
    assert r["metrics"]["overall_throughput_ops_per_sec"] > 0
    assert "ycsb.sh run basic" in r["command"]


def _make_csv(path, seconds=1500, nodes=4, seed=5):
    from simulator import ClusterSimulator, WorkloadConfig
    import csv
    sim = ClusterSimulator(num_nodes=nodes, seed=seed)
    cfg = WorkloadConfig(workload="B", seed=seed, request_rate=1000.0,
                         burst_multiplier=3.0, burst_start=240, burst_duration=150, burst_period=600)
    sim.set_workload(cfg)
    cols = datasets.REQUIRED_COLUMNS
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for _ in range(seconds):
            t = sim.step()
            for nid, n in t.items():
                w.writerow({c: n[c] for c in cols})


def test_csv_validate_rejects_bad(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("a,b,c\n1,2,3\n")
    with pytest.raises(ValueError):
        datasets.validate_and_save("bad.csv", bad.read_bytes())


def test_csv_pipeline_consumed(tmp_path, monkeypatch):
    monkeypatch.setattr(datasets, "UPLOAD_DIR", tmp_path)
    src = tmp_path / "trace_src.csv"
    _make_csv(src, seconds=1200)
    summary = datasets.validate_and_save("trace_src.csv", src.read_bytes())
    assert summary["provenance"] == "IMPORTED_CSV"
    fp = datasets.load_as_pipeline("trace_src", window_size=60, seq_len=10)
    X, y, meta = fp.sequences_with_labels(horizon_windows=5, hotspot_threshold=0.6)
    assert len(X) >= 20 and X.shape[-1] == 17
    assert 0 < y.sum() < len(y)


def test_persistence_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(persistence, "REGISTRY_DIR", tmp_path)
    monkeypatch.setattr(persistence, "META_FILE", tmp_path / "registry.json")
    monkeypatch.setattr(persistence, "ACTIVE_FILE", tmp_path / "active_model.txt")
    from models_ml import SeqModel
    m = SeqModel(input_dim=17, hidden=8, kind="gru")
    entry = {"kind": "gru", "model": m}
    record = {"name": "gru-test", "kind": "gru", "metrics": {"f1": 0.5}, "inference_ms": 1.0,
              "elapsed_ms": 1, "history": [], "config": {}, "feature_names": []}
    persistence.save_model("gru-test", entry, record)
    persistence.set_active("gru-test")
    loaded = persistence.load_all()
    assert "gru-test" in loaded
    assert loaded["gru-test"]["record"]["metrics"]["f1"] == 0.5
    assert persistence.load_active() == "gru-test"
    # weights actually load and predict
    X = np.random.rand(2, 10, 17).astype(np.float32)
    from models_ml import predict_seq
    p = predict_seq(loaded["gru-test"]["model"], X)
    assert p.shape == (2,)
