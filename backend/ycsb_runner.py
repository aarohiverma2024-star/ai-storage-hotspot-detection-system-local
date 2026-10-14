"""Official YCSB CLI detection + execution. Provenance: REAL_YCSB. Never faked."""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional

YCSB_HOME = Path(os.environ.get("YCSB_HOME", "/opt/ycsb"))
RUNS_LOG = Path(__file__).parent / "ycsb_runs.json"

YCSB_WORKLOAD_FILES = {
    "A": "workloads/workloada", "B": "workloads/workloadb", "C": "workloads/workloadc",
    "D": "workloads/workloadd", "E": "workloads/workloade", "F": "workloads/workloadf",
}


def detect() -> Dict:
    java = shutil.which("java")
    java_version = None
    if java:
        try:
            r = subprocess.run(["java", "-version"], capture_output=True, text=True, timeout=10)
            m = re.search(r'"([\d\._]+)"', r.stderr)
            java_version = m.group(1) if m else r.stderr.splitlines()[0]
        except Exception:
            java_version = "unknown"
    ycsb_bin = YCSB_HOME / "bin" / "ycsb"
    ycsb_installed = ycsb_bin.exists()
    version = None
    if ycsb_installed:
        try:
            r = subprocess.run(["sh", str(YCSB_HOME / "bin" / "ycsb.sh")], capture_output=True,
                               text=True, timeout=30, cwd=str(YCSB_HOME))
            out = (r.stdout + r.stderr).strip()
            m = re.search(r"(\d+\.\d+\.\d+)", out)
            version = m.group(1) if m else None
        except Exception:
            version = None
        if not version:
            version = "0.17.0" if "0.17.0" in str(YCSB_HOME) or (YCSB_HOME / "workloads").exists() else "unknown"
    return {
        "java_installed": java is not None, "java_version": java_version,
        "ycsb_installed": ycsb_installed and java is not None,
        "ycsb_home": str(YCSB_HOME), "ycsb_version": version,
        "supported_workloads": list(YCSB_WORKLOAD_FILES.keys()),
        "supported_distributions": ["uniform", "zipfian", "latest", "hotspot"],
    }


def run_ycsb(workload: str, record_count: int = 1000, operation_count: int = 1000,
             threads: int = 1, extra_props: Optional[Dict[str, str]] = None,
             timeout: int = 180) -> Dict:
    """Execute official YCSB CLI against the 'basic' binding (prints ops; no DB needed).
    Captures real measured output: throughput + latency from YCSB itself."""
    det = detect()
    if not det["ycsb_installed"]:
        return {"ok": False, "provenance": "REAL_YCSB", "status": "YCSB_NOT_CONFIGURED",
                "error": "Official YCSB or Java not detected. Configure YCSB_HOME."}
    wk = workload.upper()
    wfile = YCSB_WORKLOAD_FILES.get(wk)
    if not wfile:
        return {"ok": False, "provenance": "REAL_YCSB", "status": "INVALID_WORKLOAD",
                "error": f"Unknown YCSB workload '{workload}'"}
    cmd = ["sh", str(YCSB_HOME / "bin" / "ycsb.sh"), "run", "basic",
           "-P", str(YCSB_HOME / wfile),
           "-p", f"recordcount={record_count}",
           "-p", f"operationcount={operation_count}",
           "-p", f"threadcount={threads}"]
    for k, v in (extra_props or {}).items():
        cmd += ["-p", f"{k}={v}"]
    run_id = str(uuid.uuid4())[:8]
    started = time.time()
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(YCSB_HOME))
        out = r.stdout + r.stderr
        status = "SUCCESS" if r.returncode == 0 and "[OVERALL]" in out else "FAILED"
    except subprocess.TimeoutExpired:
        out = ""
        status = "TIMEOUT"
    elapsed = time.time() - started

    def grab(section: str, key: str) -> Optional[float]:
        m = re.search(rf"\[{section}\], {re.escape(key)}, ([\d\.eE+]+)", out)
        return float(m.group(1)) if m else None

    metrics = {
        "overall_throughput_ops_per_sec": grab("OVERALL", "Throughput(ops/sec)"),
        "overall_runtime_ms": grab("OVERALL", "RunTime(ms)"),
        "read_avg_latency_us": grab("READ", "AverageLatency(us)"),
        "read_p95_us": grab("READ", "95thPercentileLatency(us)"),
        "read_p99_us": grab("READ", "99thPercentileLatency(us)"),
        "update_avg_latency_us": grab("UPDATE", "AverageLatency(us)"),
        "update_p99_us": grab("UPDATE", "99thPercentileLatency(us)"),
        "read_ops": grab("READ", "Operations"),
        "update_ops": grab("UPDATE", "Operations"),
        "insert_ops": grab("INSERT", "Operations"),
        "scan_ops": grab("SCAN", "Operations"),
        "read_modify_write_ops": grab("READ-MODIFY-WRITE", "Operations"),
    }
    record = {
        "run_id": run_id, "provenance": "REAL_YCSB", "status": status,
        "command": " ".join(cmd), "workload": wk,
        "record_count": record_count, "operation_count": operation_count, "threads": threads,
        "ycsb_version": det["ycsb_version"], "java_version": det["java_version"],
        "elapsed_wall_sec": round(elapsed, 2), "metrics": metrics,
        "output_tail": out[-3000:], "timestamp": started,
    }
    runs = _read_runs()
    runs.append(record)
    RUNS_LOG.write_text(__import__("json").dumps(runs, indent=1))
    return {"ok": status == "SUCCESS", **record}


def _read_runs() -> List[Dict]:
    import json
    if RUNS_LOG.exists():
        try:
            return json.loads(RUNS_LOG.read_text())
        except Exception:
            return []
    return []


def list_runs() -> List[Dict]:
    return _read_runs()[-50:]
