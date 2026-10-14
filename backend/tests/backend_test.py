"""Backend integration tests for Predictive Storage Guardian.

Covers:
- Health endpoint (YCSB NOT_CONFIGURED badge honesty)
- Workload lifecycle (start/cluster/stop)
- Model training (threshold + gru)
- Decision engine
- Mitigation simulate
- What-if trace
"""

import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE_URL}/api/v1"


@pytest.fixture(scope="session")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# ---------- Health ----------
def test_health(s):
    r = s.get(f"{API}/health", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "ok"
    assert d["ycsb_status"] in ("CONFIGURED", "NOT_CONFIGURED_SYNTHETIC_MODE")


# ---------- Workload lifecycle ----------
def test_workload_lifecycle(s):
    r = s.post(f"{API}/workloads/start", json={"workload": "B", "request_rate": 900, "num_nodes": 4}, timeout=15)
    assert r.status_code == 200, r.text
    time.sleep(2)
    c = s.get(f"{API}/cluster", timeout=15)
    assert c.status_code == 200
    cd = c.json()
    assert cd.get("running") is True
    nodes = cd.get("nodes", [])
    assert len(nodes) == 4, f"expected 4 nodes, got {len(nodes)}"
    for n in nodes:
        assert "load" in n and "p99_latency_ms" in n or "p99" in n or "p99_ms" in n
    # stop (leave state intact; workload can restart)
    st = s.post(f"{API}/workloads/stop", timeout=15)
    assert st.status_code == 200


# ---------- Training ----------
def test_train_threshold(s):
    r = s.post(f"{API}/models/train", json={"model_kind": "threshold"}, timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    m = d["model"]["metrics"]
    assert "f1" in m and "auc" in m
    assert isinstance(m["f1"], (int, float))
    assert "confusion" in m
    assert d["model"]["name"].startswith("threshold-")


def test_train_gru(s):
    r = s.post(f"{API}/models/train", json={"model_kind": "gru", "epochs": 4, "hidden": 16}, timeout=180)
    assert r.status_code == 200, r.text
    d = r.json()
    m = d["model"]["metrics"]
    assert "f1" in m and "auc" in m
    assert 0.0 <= float(m["f1"]) <= 1.0
    assert d["model"]["kind"] == "gru"


# ---------- Decision ----------
def test_decision(s):
    payload = {
        "probability": 0.8,
        "confidence": 0.9,
        "read_ratio": 0.9,
        "cache_hit_rate": 0.6,
        "node_load": 0.7,
    }
    r = s.post(f"{API}/decision", json=payload, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "action" in d
    # reason/cost/benefit fields
    keys = set(d.keys())
    assert keys & {"reason", "rationale", "explanation"}
    assert keys & {"cost", "expected_cost"}
    assert keys & {"benefit", "expected_benefit"}


# ---------- Mitigation ----------
def test_mitigation_simulate(s):
    # ensure a workload running so partitions exist
    s.post(f"{API}/workloads/start", json={"workload": "B", "request_rate": 900, "num_nodes": 4}, timeout=15)
    time.sleep(1)
    r = s.post(f"{API}/mitigation/simulate", json={"action": "REPLICATE", "partition": 0}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["result"]["ok"] is True
    assert "before" in d and "after" in d
    assert "cluster_load_mean" in d["before"]


# ---------- What-if ----------
def test_whatif(s):
    r = s.post(f"{API}/whatif", json={"action": "REPLICATE", "partition": 0, "horizon": 5}, timeout=30)
    if r.status_code != 200:
        # try minimal body
        r = s.post(f"{API}/whatif", json={}, timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    trace = d.get("trace") or d.get("steps") or d
    assert isinstance(trace, list) and len(trace) > 0
