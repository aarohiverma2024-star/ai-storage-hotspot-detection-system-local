"""FastAPI routers: all API endpoints for Predictive Storage Guardian."""
from __future__ import annotations
import time
import uuid
import numpy as np
from dataclasses import asdict
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
from pydantic import BaseModel, Field

from simulator import WorkloadConfig, YCSB_PRESETS, DISTRIBUTIONS
from features import FEATURE_NAMES
from models_ml import (
    SeqModel, train_seq, chronological_split, eval_binary,
    train_threshold_baseline, train_ma_baseline, train_classical,
    predict_threshold, predict_ma, predict_classical, predict_seq,
    perturbation_importance, StandardScaler,
)
from decision import choose_action, confidence_level, severity_from_score
from state import STATE
from datasets import validate_and_save, list_datasets, load_as_pipeline
from ycsb_runner import detect as ycsb_detect, run_ycsb, list_runs as ycsb_runs, YCSB_WORKLOAD_FILES
import persistence
import torch


import logging

logger = logging.getLogger("psg.routers")

router = APIRouter(prefix="/api/v1")


# ---------- Schemas ----------
class WorkloadRequest(BaseModel):
    workload: str = "B"
    distribution: str = "zipfian"
    read_pct: float = 0.95
    update_pct: float = 0.05
    insert_pct: float = 0.0
    scan_pct: float = 0.0
    rmw_pct: float = 0.0
    record_count: int = 10000
    operation_count: int = 500000
    request_rate: float = 800.0
    zipfian_theta: float = 0.99
    hot_key_pct: float = 0.01
    hot_key_traffic_share: float = 0.4
    duration_sec: int = 300
    seed: int = 42
    burst_multiplier: float = 1.0
    burst_start: int = -1
    burst_duration: int = 30
    num_nodes: Optional[int] = 4


class TrainRequest(BaseModel):
    model_kind: str = "gru"  # gru, lstm, lr, rf, threshold, moving_average
    dataset: str = "simulator"  # "simulator" or "csv:<name>"
    seq_len: int = 10
    horizon_windows: int = 5  # each window = 60s, so 5 windows = 5 min
    hotspot_threshold: float = 0.6
    hidden: int = 32
    layers: int = 1
    dropout: float = 0.15
    lr: float = 1e-3
    epochs: int = 12
    batch: int = 64
    workload_key: str = "B"
    seed: int = 42
    num_nodes: int = 4
    warmup_sim_seconds: int = 3600  # ~60 min of sim data


class DecisionRequest(BaseModel):
    node_id: Optional[str] = None
    probability: float
    confidence: float
    lead_time_sec: float = 300.0
    read_ratio: float = 0.9
    write_ratio: float = 0.1
    access_concentration: float = 0.5
    cache_hit_rate: float = 0.7
    node_load: float = 0.7
    cluster_headroom: float = 0.4
    partition_size_mb: Optional[float] = 500.0
    network_bandwidth_mbps: Optional[float] = 100.0
    safety_margin_sec: Optional[float] = 15.0


class MitigationRequest(BaseModel):
    action: str  # REPLICATE / MIGRATE / CACHE_PROMOTION / THROTTLE
    node_id: Optional[str] = None
    partition: Optional[int] = None
    destination: Optional[str] = None
    throttle_pct: Optional[float] = 0.2
    simulate_only: bool = True
    duration_sec: Optional[float] = 0.0
    estimated_duration_sec: Optional[float] = None
    lead_time_sec: Optional[float] = None
    buffer_time_sec: Optional[float] = None
    downgraded: Optional[bool] = False
    buffer_status: Optional[str] = None



class WhatIfRequest(BaseModel):
    request_rate: float = 1500.0
    zipfian_theta: float = 1.1
    hot_key_traffic_share: float = 0.7
    read_pct: float = 0.9
    num_nodes: int = 4
    seed: int = 7
    steps: int = 300  # sim seconds


# ---------- Health ----------
@router.get("/health")
def health():
    ycsb_on = ycsb_detect()["ycsb_installed"]
    return {"status": "ok", "service": "predictive-storage-guardian",
            "sim_running": STATE.running, "t_sim": STATE.sim.t_sec,
            "active_model": STATE.active_model,
            "models_registered": list(STATE.models.keys()),
            "models_persisted": len(persistence.load_all()) if persistence.META_FILE.exists() else 0,
            "ycsb_status": "CONFIGURED" if ycsb_on else "NOT_CONFIGURED_SYNTHETIC_MODE"}


@router.get("/ycsb/validate")
def ycsb_validate():
    det = ycsb_detect()
    det["message"] = (
        f"Official YCSB {det['ycsb_version']} detected (Java {det['java_version']}). Ready to execute real YCSB workloads."
        if det["ycsb_installed"] else
        "YCSB CLI not present. Using embedded YCSB-compatible generator (workloads A-F, distributions, tunable mix).")
    return det


class YcsbRunRequest(BaseModel):
    workload: str = "A"
    record_count: int = 1000
    operation_count: int = 1000
    threads: int = 1
    extra_props: Optional[Dict[str, str]] = None


@router.post("/ycsb/run")
def ycsb_run(req: YcsbRunRequest):
    """Execute the OFFICIAL YCSB CLI (basic binding) and capture real measured output."""
    result = run_ycsb(req.workload, req.record_count, req.operation_count, req.threads, req.extra_props)
    STATE.audit.append({"ts": time.time(), "user": "operator",
                        "event": f"ycsb_run:{req.workload}", "status": result.get("status")})
    if not result["ok"]:
        raise HTTPException(400, result.get("error") or f"YCSB run status: {result.get('status')}")
    return result


@router.get("/ycsb/runs")
def ycsb_run_history():
    return {"runs": ycsb_runs(), "workload_files": YCSB_WORKLOAD_FILES}


# ---------- Datasets (CSV) ----------
@router.post("/datasets/upload")
async def dataset_upload(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Only .csv telemetry files are accepted.")
    content = await file.read()
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(400, "File too large (max 50MB).")
    try:
        summary = validate_and_save(file.filename, content)
    except ValueError as e:
        raise HTTPException(400, str(e))
    STATE.audit.append({"ts": time.time(), "user": "operator",
                        "event": f"dataset_upload:{summary['name']}", "rows": summary["rows"]})
    return {"ok": True, **summary}


@router.get("/datasets")
def datasets_list():
    return {"datasets": list_datasets()}


# ---------- Cluster / Telemetry ----------
@router.get("/cluster")
def cluster():
    return STATE.cluster_snapshot()


@router.get("/telemetry")
def telemetry(limit: int = 120):
    hist = list(STATE.telemetry_history)[-limit:]
    return {"count": len(hist), "history": hist}


@router.get("/telemetry/node/{node_id}")
def telemetry_node(node_id: str, limit: int = 120):
    out = []
    for snap in list(STATE.telemetry_history)[-limit:]:
        if node_id in snap["nodes"]:
            out.append({"t": snap["t"], **snap["nodes"][node_id]})
    return {"node_id": node_id, "history": out}


# ---------- Workloads ----------
@router.post("/workloads/start")
def workload_start(req: WorkloadRequest):
    cfg = WorkloadConfig(**{k: v for k, v in req.dict().items() if k != "num_nodes"})
    STATE.start(cfg, num_nodes=req.num_nodes)
    return {"ok": True, "workload": cfg.__dict__, "num_nodes": STATE.sim.num_nodes}


@router.post("/workloads/stop")
def workload_stop():
    STATE.stop()
    return {"ok": True}


@router.post("/workloads/reset")
def workload_reset():
    STATE.reset()
    return {"ok": True}


@router.get("/workloads/presets")
def workload_presets():
    return {"ycsb": YCSB_PRESETS, "distributions": DISTRIBUTIONS}


# ---------- Training ----------
def _collect_training_data(req: TrainRequest):
    """Produce training sequences from the simulator OR an uploaded CSV dataset."""
    if req.dataset.startswith("csv:"):
        name = req.dataset[4:]
        try:
            pipeline = load_as_pipeline(name, window_size=60, seq_len=req.seq_len)
        except ValueError as e:
            raise HTTPException(400, str(e))
        X, y, meta = pipeline.sequences_with_labels(horizon_windows=req.horizon_windows,
                                                     hotspot_threshold=req.hotspot_threshold)
        for m in meta:
            m["provenance"] = "IMPORTED_CSV"
        return X, y, meta
    from simulator import ClusterSimulator, WorkloadConfig
    from features import FeaturePipeline
    sim = ClusterSimulator(num_nodes=req.num_nodes, seed=req.seed)
    cfg = WorkloadConfig(workload=req.workload_key, seed=req.seed,
                         request_rate=1000.0, hot_key_traffic_share=0.55,
                         zipfian_theta=1.0, burst_multiplier=3.0,
                         burst_start=240, burst_duration=150, burst_period=600)
    sim.set_workload(cfg)
    pipeline = FeaturePipeline(window_size=60, seq_len=req.seq_len)
    for _ in range(req.warmup_sim_seconds):
        telem = sim.step()
        pipeline.add_second(telem)
    pipeline.build_features()
    X, y, meta = pipeline.sequences_with_labels(horizon_windows=req.horizon_windows,
                                                 hotspot_threshold=req.hotspot_threshold)
    return X, y, meta


@router.post("/models/train")
def train_model(req: TrainRequest):
    job_id = str(uuid.uuid4())[:8]
    STATE.training_jobs[job_id] = {"status": "running", "history": [], "started": time.time()}
    try:
        X, y, meta = _collect_training_data(req)
        if len(X) < 40:
            STATE.training_jobs[job_id]["status"] = "failed"
            STATE.training_jobs[job_id]["error"] = f"Insufficient samples ({len(X)}); increase warmup_sim_seconds."
            raise HTTPException(400, STATE.training_jobs[job_id]["error"])
        pos = int(y.sum()); neg = int(len(y) - y.sum())
        if pos < 2 or neg < 2:
            # Degenerate label distribution: fall back to score-quantile labels
            # (still future-observation based, no leakage — only labels change)
            fut = np.array([m["future_hotspot_score"] for m in meta])
            q = float(np.quantile(fut, 0.35))
            y = (fut >= q).astype(np.int64)
            pos = int(y.sum()); neg = int(len(y) - y.sum())
            if pos < 2 or neg < 2:
                STATE.training_jobs[job_id]["status"] = "failed"
                STATE.training_jobs[job_id]["error"] = "Degenerate label distribution even after quantile fallback."
                raise HTTPException(400, STATE.training_jobs[job_id]["error"])
        # True chronological split by window time index (nodes share t_index)
        t_idx = np.array([m["t_index"] for m in meta])
        tmax = max(1, int(t_idx.max()))
        tr_m = t_idx < int(tmax * 0.70)
        va_m = (t_idx >= int(tmax * 0.70)) & (t_idx < int(tmax * 0.85))
        te_m = t_idx >= int(tmax * 0.85)
        X_tr, y_tr = X[tr_m], y[tr_m]
        X_val, y_val = X[va_m], y[va_m]
        X_te, y_te = X[te_m], y[te_m]
        if len(X_te) == 0 or len(np.unique(y_te)) < 2 or len(np.unique(y_tr)) < 2:
            # fall back to contiguous block split
            (X_tr, y_tr), (X_val, y_val), (X_te, y_te) = chronological_split(X, y)
        model_name = f"{req.model_kind}-{job_id}"
        t0 = time.time()
        # Fit scaler on TRAIN only (per-feature across time steps) — never on test
        scaler = StandardScaler()
        F = X.shape[-1]
        scaler.fit(X_tr.reshape(-1, F))
        def scale(a): return scaler.transform(a.reshape(-1, F)).reshape(a.shape)
        X_tr_s, X_val_s, X_te_s = scale(X_tr), scale(X_val), scale(X_te)
        if req.model_kind in ("gru", "lstm"):
            m = SeqModel(input_dim=F, hidden=req.hidden, layers=req.layers,
                         dropout=req.dropout, kind=req.model_kind)
            hist = train_seq(m, X_tr_s, y_tr, X_val_s, y_val, lr=req.lr, epochs=req.epochs,
                             batch=req.batch, on_epoch=lambda h: STATE.training_jobs[job_id]["history"].append(h))
            probs_te = predict_seq(m, X_te_s)
            entry = {"kind": req.model_kind, "model": m, "scaler": scaler}
        elif req.model_kind == "threshold":
            entry = train_threshold_baseline(X_tr_s, y_tr)
            entry["scaler"] = scaler
            probs_te = predict_threshold(entry, X_te_s)
            hist = {"history": []}
        elif req.model_kind == "moving_average":
            entry = train_ma_baseline(X_tr_s, y_tr)
            entry["scaler"] = scaler
            probs_te = predict_ma(entry, X_te_s)
            hist = {"history": []}
        elif req.model_kind in ("lr", "rf"):
            entry = train_classical(X_tr, y_tr, kind=req.model_kind)  # internal scaler
            probs_te = predict_classical(entry, X_te)
            hist = {"history": []}
        else:
            raise HTTPException(400, f"Unknown model kind {req.model_kind}")
        elapsed_ms = (time.time() - t0) * 1000
        metrics = eval_binary(y_te, probs_te)
        # Inference latency (batch of 1, after one warmup call)
        _ = STATE._infer(entry, X_te[:1])
        t1 = time.time()
        _ = STATE._infer(entry, X_te[:1])
        infer_ms = (time.time() - t1) * 1000
        model_record = {
            "name": model_name, "kind": req.model_kind,
            "trained_at": time.time(), "elapsed_ms": round(elapsed_ms, 1),
            "inference_ms": round(infer_ms, 3),
            "metrics": metrics,
            "history": hist.get("history", []) if isinstance(hist, dict) else [],
            "config": req.dict(), "feature_names": FEATURE_NAMES,
            "n_train": len(X_tr), "n_val": len(X_val), "n_test": len(X_te),
            "positive_rate": float(y.mean()),
        }
        STATE.models[model_name] = {**entry, "record": model_record}
        # Persist weights + scaler + metadata so registry survives restarts
        try:
            persistence.save_model(model_name, entry, model_record)
        except Exception as pe:
            logger.warning(f"persist failed for {model_name}: {pe}")
        # Set as active if it's the first neural model
        if STATE.active_model is None or req.model_kind in ("gru", "lstm"):
            STATE.active_model = model_name
        STATE.training_jobs[job_id]["status"] = "done"
        STATE.training_jobs[job_id]["model_name"] = model_name
        STATE.training_jobs[job_id]["metrics"] = metrics
        return {"job_id": job_id, "model": model_record, "test_set": {"n": len(X_te),
                "positives": int(y_te.sum()), "negatives": int((y_te == 0).sum())}}
    except HTTPException:
        raise
    except Exception as e:
        STATE.training_jobs[job_id]["status"] = "failed"
        STATE.training_jobs[job_id]["error"] = str(e)
        raise HTTPException(500, str(e))


@router.get("/models")
def list_models():
    return {"active": STATE.active_model,
            "models": [m["record"] for m in STATE.models.values()]}


@router.post("/models/{model_name}/activate")
def activate_model(model_name: str):
    if model_name not in STATE.models:
        raise HTTPException(404, "Model not found")
    STATE.active_model = model_name
    persistence.set_active(model_name)
    return {"ok": True, "active": model_name}


@router.get("/models/comparison")
def compare_models():
    rows = []
    for m in STATE.models.values():
        r = m["record"]
        rows.append({"name": r["name"], "kind": r["kind"],
                     "precision": r["metrics"]["precision"],
                     "recall": r["metrics"]["recall"], "f1": r["metrics"]["f1"],
                     "auc": r["metrics"]["auc"],
                     "inference_ms": r["inference_ms"], "elapsed_ms": r["elapsed_ms"]})
    return {"models": rows}


# ---------- Prediction / Explanation ----------
@router.get("/predictions")
def predictions(limit: int = 50):
    return {"predictions": STATE.recent_predictions[-limit:],
            "active_model": STATE.active_model}


@router.get("/hotspots")
def hotspots():
    """Merge current telemetry + last prediction per node."""
    snap = STATE.cluster_snapshot()
    by_node = {n["node_id"]: n for n in snap["nodes"]}
    preds_by_node: Dict[str, Dict] = {}
    for p in STATE.recent_predictions:
        preds_by_node[p["node_id"]] = p
    rows = []
    for nid, n in by_node.items():
        p = preds_by_node.get(nid)
        rows.append({
            "node_id": nid, "current_load": n["load"], "current_hotspot_score": n["hotspot_score"],
            "queue_depth": n["queue_depth"], "p95_latency_ms": n["p95_latency_ms"],
            "p99_latency_ms": n["p99_latency_ms"], "cache_hit_rate": n["cache_hit_rate"],
            "tier": n["tier"],
            "predicted_probability": p["hotspot_probability"] if p else None,
            "confidence": p["confidence"] if p else None,
            "confidence_level": p["confidence_level"] if p else None,
            "severity": p["severity"] if p else severity_from_score(n["hotspot_score"]),
            "model_name": p["model_name"] if p else None,
        })
    return {"rows": rows, "active_model": STATE.active_model}


@router.get("/explain/{node_id}")
def explain(node_id: str):
    if not STATE.active_model or STATE.active_model not in STATE.models:
        raise HTTPException(400, "No active model")
    entry = STATE.models[STATE.active_model]
    feats = STATE.pipeline.features.get(node_id)
    if not feats or len(feats) < STATE.pipeline.seq_len:
        raise HTTPException(400, "Not enough feature history yet")
    seq = feats[-STATE.pipeline.seq_len:]
    X = np.array([seq], dtype=np.float32)
    baseline = float(STATE._infer(entry, X)[0])

    def predictor(_entry, x): return STATE._infer(_entry, x)
    contribs = perturbation_importance(entry, predictor, X, FEATURE_NAMES, baseline_prob=baseline)
    return {"node_id": node_id, "baseline_probability": round(baseline, 4),
            "feature_names": FEATURE_NAMES, "contributions": contribs}


# ---------- Decision + Mitigation ----------
@router.post("/decision")
def decision(req: DecisionRequest):
    ctx = req.dict()
    sev = severity_from_score(req.probability)
    ctx["severity"] = sev
    result = choose_action(ctx)
    result["severity"] = sev
    return result


@router.post("/mitigation/simulate")
def mitigation_simulate(req: MitigationRequest):
    """Apply mitigation and record before/after metrics after brief simulation."""
    before = STATE.cluster_snapshot()
    before_metrics = {"cluster_load_mean": before["cluster_load_mean"],
                      "cluster_load_cv": before["cluster_load_cv"],
                      "avg_p95": float(np.mean([n["p95_latency_ms"] for n in before["nodes"]])) if before["nodes"] else 0,
                      "avg_p99": float(np.mean([n["p99_latency_ms"] for n in before["nodes"]])) if before["nodes"] else 0,
                      "avg_queue": float(np.mean([n["queue_depth"] for n in before["nodes"]])) if before["nodes"] else 0,
                      }
    result = {"ok": False}
    action = req.action.upper()
    duration = req.duration_sec or 0.0
    if action == "REPLICATE":
        partition = req.partition if req.partition is not None else 0
        result = STATE.sim.replicate(partition, req.destination, duration_sec=duration)
    elif action == "MIGRATE":
        partition = req.partition if req.partition is not None else 0
        result = STATE.sim.migrate(partition, req.destination, duration_sec=duration)
    elif action == "CACHE_PROMOTION":
        partition = req.partition if req.partition is not None else 0
        result = STATE.sim.promote_cache(partition)
    elif action == "THROTTLE":
        node_id = req.node_id or list(STATE.sim.nodes.keys())[0]
        result = STATE.sim.throttle(node_id, req.throttle_pct or 0.2)
    else:
        raise HTTPException(400, "Unknown action")
    # Run 30 sim seconds to observe effect (only if simulation running; otherwise force manual steps)
    if not STATE.running:
        if STATE.sim.workload is None:
            STATE.sim.set_workload(WorkloadConfig(workload="B", seed=42))
        # Force a lightweight simulation step
        for _ in range(30):
            STATE.sim.step()
    else:
        time.sleep(1.2)  # let bg thread advance
    after = STATE.cluster_snapshot()
    after_metrics = {"cluster_load_mean": after["cluster_load_mean"],
                     "cluster_load_cv": after["cluster_load_cv"],
                     "avg_p95": float(np.mean([n["p95_latency_ms"] for n in after["nodes"]])) if after["nodes"] else 0,
                     "avg_p99": float(np.mean([n["p99_latency_ms"] for n in after["nodes"]])) if after["nodes"] else 0,
                     "avg_queue": float(np.mean([n["queue_depth"] for n in after["nodes"]])) if after["nodes"] else 0,
                     }

    buffer_deadline_met = True
    if req.lead_time_sec is not None and req.estimated_duration_sec is not None:
        buffer_deadline_met = bool(req.lead_time_sec >= req.estimated_duration_sec)

    log = {
        "id": str(uuid.uuid4())[:8], "timestamp": time.time(),
        "action": action, "params": req.dict(),
        "result": result,
        "before": before_metrics, "after": after_metrics,
        "buffer_telemetry": {
            "lead_time_sec": req.lead_time_sec,
            "estimated_duration_sec": req.estimated_duration_sec,
            "buffer_time_sec": req.buffer_time_sec,
            "buffer_deadline_met": buffer_deadline_met,
            "downgraded": req.downgraded,
            "buffer_status": req.buffer_status,
        }
    }
    STATE.mitigations.append(log)
    STATE.audit.append({"ts": time.time(), "user": "operator", "event": f"mitigation:{action}",
                        "params": req.dict(), "buffer_telemetry": log["buffer_telemetry"]})
    return log



@router.get("/mitigations")
def get_mitigations():
    return {"mitigations": STATE.mitigations[-50:]}


# ---------- What-If ----------
@router.post("/whatif")
def whatif(req: WhatIfRequest):
    from simulator import ClusterSimulator, WorkloadConfig
    sim = ClusterSimulator(num_nodes=req.num_nodes, seed=req.seed)
    cfg = WorkloadConfig(seed=req.seed, request_rate=req.request_rate,
                         zipfian_theta=req.zipfian_theta,
                         hot_key_traffic_share=req.hot_key_traffic_share,
                         read_pct=req.read_pct, update_pct=1 - req.read_pct)
    sim.set_workload(cfg)
    trace = []
    for _ in range(req.steps):
        t = sim.step()
        loads = [n["load"] for n in t.values()]
        p99 = [n["p99_latency_ms"] for n in t.values()]
        trace.append({"t": sim.t_sec, "load_max": max(loads), "load_mean": float(np.mean(loads)),
                      "p99_max": max(p99), "hotspot_max": max(n["hotspot_score"] for n in t.values())})
    return {"trace": trace, "final": [asdict(n) for n in sim.nodes.values()]}


# ---------- Experiments ----------
class ExperimentRequest(BaseModel):
    workload_keys: List[str] = ["B", "A"]
    model_kinds: List[str] = ["threshold", "moving_average", "lr", "gru"]
    seed: int = 42
    warmup_sim_seconds: int = 1200
    horizon_windows: int = 5
    hotspot_threshold: float = 0.6


@router.post("/experiments/run")
def run_experiments(req: ExperimentRequest):
    results = []
    for wk in req.workload_keys:
        for mk in req.model_kinds:
            tr = TrainRequest(model_kind=mk, workload_key=wk, seed=req.seed,
                              warmup_sim_seconds=req.warmup_sim_seconds,
                              horizon_windows=req.horizon_windows,
                              hotspot_threshold=req.hotspot_threshold)
            try:
                r = train_model(tr)
                results.append({"workload": wk, "model": mk, "ok": True,
                                "metrics": r["model"]["metrics"],
                                "inference_ms": r["model"]["inference_ms"]})
            except Exception as e:
                results.append({"workload": wk, "model": mk, "ok": False, "error": str(e)})
    exp = {"id": str(uuid.uuid4())[:8], "timestamp": time.time(),
           "config": req.dict(), "results": results}
    STATE.experiments.append(exp)
    return exp


@router.get("/experiments")
def get_experiments():
    return {"experiments": STATE.experiments[-20:]}


# ---------- Demo ----------
@router.post("/demo/start")
def demo_start():
    cfg = WorkloadConfig(workload="B", seed=42, request_rate=1200.0,
                         hot_key_traffic_share=0.6, zipfian_theta=1.0,
                         burst_multiplier=3.5, burst_start=60, burst_duration=180)
    STATE.start(cfg, num_nodes=4)
    # ensure at least one lightweight active model exists
    if STATE.active_model is None:
        try:
            train_model(TrainRequest(model_kind="threshold", warmup_sim_seconds=1800, hotspot_threshold=0.5))
        except Exception:
            pass
    return {"ok": True, "scenario": "flash-crowd on hot key range"}


@router.post("/demo/reset")
def demo_reset():
    STATE.reset()
    return {"ok": True}


# ---------- Audit / Config ----------
@router.get("/audit")
def audit():
    return {"audit": STATE.audit[-100:]}


@router.get("/features/schema")
def features_schema():
    return {"features": FEATURE_NAMES}
