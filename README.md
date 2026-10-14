# Predictive Storage Guardian

**Predict. Explain. Prevent.**

Research-grade predictive storage hotspot detection and cross-layer mitigation, extending the *observe-and-tune* concept from **"Improving Storage Systems Using Machine Learning" (KML, Akgun et al.)** from reactive workload classification to **predictive, confidence-aware hotspot forecasting** with **cross-layer mitigation** (replicate / migrate / cache-promote / throttle).

## Research Statement

> We extend ML-based observe-and-tune storage optimization from reactive workload classification and single-parameter tuning to predictive, confidence-aware hotspot forecasting and cross-layer mitigation.

## Quick Start

```bash
# Backend (FastAPI, port 8001)
cd backend && pip install -r requirements.txt
uvicorn server:app --host 0.0.0.0 --port 8001

# Frontend (React, port 3000)
cd frontend && yarn install && yarn start
```

Or with Docker: `docker compose up --build`

## Demo

Open the dashboard → **Demo Mode** → **Start Demo**. The orchestrator runs: reset → YCSB-B flash-crowd workload → GRU training → live predictions → explanation → decision → simulated mitigation → before/after metrics.

## Stack

- **Backend**: FastAPI + PyTorch (GRU/LSTM) + scikit-learn (LR/RF) + NumPy
- **Simulator**: deterministic trace-driven storage cluster simulator (YCSB-compatible workload generator, workloads A–F, uniform/zipfian/latest/hotkey/hotspot distributions)
- **DB**: MongoDB (environment-provided; PostgreSQL-equivalent schema documented in docs/DATABASE.md)
- **Frontend**: React + Tailwind + Recharts

## Pipeline

```
YCSB-compatible workload → Storage cluster simulator → Telemetry (1s)
  → 60s aggregation windows → temporal features → sequences (10 windows)
  → GRU/LSTM/LR/RF/Threshold/MA → future-hotspot probability + confidence
  → perturbation explanation → decision engine (guardrails)
  → simulated mitigation → before/after measurement → feedback
```

## Docs

See `/docs`: ARCHITECTURE, METHODOLOGY, DATASET, YCSB_INTEGRATION, ML_MODEL, EVALUATION, API, DEMO_GUIDE, RESEARCH_MAPPING, PATENT_ORIENTED_CONTRIBUTION, LIMITATIONS, DEPLOYMENT.
