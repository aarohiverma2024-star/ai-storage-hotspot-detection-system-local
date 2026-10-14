"""CSV dataset ingestion: validate → normalize → FeaturePipeline-ready rows."""
from __future__ import annotations
import io
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

UPLOAD_DIR = Path(__file__).parent / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

REQUIRED_COLUMNS = [
    "node_id", "t", "read_iops", "write_iops", "throughput_mbps", "cpu", "memory",
    "storage", "queue_depth", "avg_latency_ms", "p95_latency_ms", "p99_latency_ms",
    "cache_hit_rate", "load", "hotspot_score",
]


def validate_and_save(filename: str, content: bytes) -> Dict:
    """Parse + validate a telemetry CSV. Returns summary or raises ValueError."""
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception as e:
        raise ValueError(f"Not a parseable CSV: {e}")
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Required: {REQUIRED_COLUMNS}")
    if len(df) < 120:
        raise ValueError(f"Need at least 120 rows (got {len(df)}) to form aggregation windows.")
    df = df.sort_values(["t", "node_id"]).reset_index(drop=True)
    name = Path(filename).stem.replace("/", "_").replace("..", "_")
    out = UPLOAD_DIR / f"{name}.csv"
    df.to_csv(out, index=False)
    return {
        "name": name, "path": str(out), "rows": len(df),
        "nodes": sorted(df["node_id"].unique().tolist()),
        "t_range": [int(df["t"].min()), int(df["t"].max())],
        "columns": df.columns.tolist(),
        "provenance": "IMPORTED_CSV",
    }


def list_datasets() -> List[Dict]:
    out = []
    for p in sorted(UPLOAD_DIR.glob("*.csv")):
        try:
            df = pd.read_csv(p, nrows=5)
            full_rows = sum(1 for _ in open(p)) - 1
            out.append({"name": p.stem, "rows": full_rows,
                        "nodes": sorted(df["node_id"].unique().tolist()) if "node_id" in df else [],
                        "provenance": "IMPORTED_CSV"})
        except Exception:
            continue
    return out


def load_as_pipeline(name: str, window_size: int = 60, seq_len: int = 10):
    """Load CSV → FeaturePipeline (windows + features). Caller generates labels."""
    from features import FeaturePipeline
    p = UPLOAD_DIR / f"{name}.csv"
    if not p.exists():
        raise ValueError(f"Dataset '{name}' not found")
    df = pd.read_csv(p).sort_values(["t", "node_id"])
    fp = FeaturePipeline(window_size=window_size, seq_len=seq_len)
    # group rows by t into per-second dicts
    for t, grp in df.groupby("t"):
        per_node = {}
        for _, r in grp.iterrows():
            per_node[str(r["node_id"])] = {
                "node_id": str(r["node_id"]), "t": int(r["t"]),
                "read_iops": float(r["read_iops"]), "write_iops": float(r["write_iops"]),
                "throughput_mbps": float(r["throughput_mbps"]),
                "cpu": float(r["cpu"]), "memory": float(r["memory"]), "storage": float(r["storage"]),
                "queue_depth": float(r["queue_depth"]),
                "avg_latency_ms": float(r["avg_latency_ms"]),
                "p95_latency_ms": float(r["p95_latency_ms"]),
                "p99_latency_ms": float(r["p99_latency_ms"]),
                "cache_hit_rate": float(r["cache_hit_rate"]),
                "load": float(r["load"]), "hotspot_score": float(r["hotspot_score"]),
            }
        fp.add_second(per_node)
    fp.build_features()
    return fp
