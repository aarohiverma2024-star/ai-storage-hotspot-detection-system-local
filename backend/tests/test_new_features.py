"""Tests for the three deferred features + regression:
- REAL YCSB CLI (detect + run + history)
- CSV upload + genuine ML consumption
- Model persistence across restart (verified indirectly via /health + /models)
"""
import os
import io
import time
import subprocess
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api/v1"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    return sess


# ---------------- REAL YCSB ----------------
def test_ycsb_validate_real(s):
    r = s.get(f"{API}/ycsb/validate", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ycsb_installed"] is True, d
    assert d["ycsb_version"] == "0.17.0", d
    assert d["java_version"] and d["java_version"].startswith(("17", "1.17")), d


def test_ycsb_run_real(s):
    r = s.post(f"{API}/ycsb/run",
               json={"workload": "B", "record_count": 500, "operation_count": 500},
               timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["provenance"] == "REAL_YCSB"
    assert d["status"] == "SUCCESS"
    assert "ycsb.sh" in d["command"]
    m = d["metrics"]
    assert m["overall_throughput_ops_per_sec"] is not None and m["overall_throughput_ops_per_sec"] > 0

    # verify listed in history
    h = s.get(f"{API}/ycsb/runs", timeout=15).json()
    runs = h["runs"]
    assert any(r_["run_id"] == d["run_id"] and r_["provenance"] == "REAL_YCSB" for r_ in runs)


# ---------------- CSV upload ----------------
def test_csv_upload_invalid(s):
    bad = b"foo,bar,baz\n1,2,3\n"
    r = s.post(f"{API}/datasets/upload",
               files={"file": ("bad.csv", bad, "text/csv")}, timeout=30)
    assert r.status_code == 400
    body = r.text.lower()
    assert "missing" in body or "required" in body


def test_csv_upload_valid_and_listed(s):
    # use existing telemetry_long.csv
    p = "/app/backend/uploads/telemetry_long.csv"
    with open(p, "rb") as f:
        content = f.read()
    r = s.post(f"{API}/datasets/upload",
               files={"file": ("telemetry_long.csv", content, "text/csv")}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True
    assert d["provenance"] == "IMPORTED_CSV"
    assert d["rows"] >= 120

    ls = s.get(f"{API}/datasets", timeout=15).json()
    assert any(x["name"] == "telemetry_long" and x["provenance"] == "IMPORTED_CSV"
               for x in ls["datasets"])


def test_train_gru_on_csv(s):
    r = s.post(f"{API}/models/train",
               json={"model_kind": "gru", "dataset": "csv:telemetry_long",
                     "epochs": 4, "hidden": 16},
               timeout=300)
    assert r.status_code == 200, r.text
    d = r.json()
    m = d["model"]["metrics"]
    assert "f1" in m and "auc" in m and "confusion" in m
    # dataset field in config confirms CSV was consumed
    assert d["model"]["config"]["dataset"] == "csv:telemetry_long"


# ---------------- Model persistence across restart ----------------
def test_model_persistence_across_restart(s):
    # Train a threshold model (fast)
    r = s.post(f"{API}/models/train",
               json={"model_kind": "threshold", "dataset": "simulator",
                     "warmup_sim_seconds": 1800},
               timeout=120)
    assert r.status_code == 200, r.text
    name = r.json()["model"]["name"]

    # baseline persisted count
    h0 = s.get(f"{API}/health", timeout=15).json()
    assert name in h0["models_registered"]
    persisted_before = h0["models_persisted"]
    assert persisted_before > 0

    # Restart backend
    subprocess.run(["sudo", "supervisorctl", "restart", "backend"],
                   check=True, capture_output=True)
    # wait for readiness
    deadline = time.time() + 40
    while time.time() < deadline:
        try:
            hr = s.get(f"{API}/health", timeout=5)
            if hr.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(1)

    h1 = s.get(f"{API}/health", timeout=15).json()
    assert h1["models_persisted"] > 0
    assert name in h1["models_registered"], f"{name} not in {h1['models_registered']}"

    ms = s.get(f"{API}/models", timeout=15).json()
    entry = next((m for m in ms["models"] if m["name"] == name), None)
    assert entry is not None
    assert "f1" in entry["metrics"]
