# Local Development (VS Code)

## 1. Extract & open

```bash
unzip Predictive-Storage-Guardian-Standalone.zip
code Predictive-Storage-Guardian
```

Open the folder `Predictive-Storage-Guardian/` (the repo root containing `backend/`, `frontend/`, `docs/`).

## 2. Prerequisites

- **Python 3.11** (3.10+ works)
- **Node.js 18+** (20 LTS recommended) + **yarn** (`npm i -g yarn`)
- **MongoDB** local or Docker: `docker run -d -p 27017:27017 mongo:7`
- Optional: Java 17 + official YCSB release for `REAL_YCSB` mode (otherwise the app runs in honestly-labeled synthetic mode)

## 3. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.4.1
```

`backend/.env` (already present with local defaults; no secrets):

```
MONGO_URL="mongodb://localhost:27017"
DB_NAME="predictive_storage_guardian"
CORS_ORIGINS="*"
```

Start:

```bash
uvicorn server:app --host 0.0.0.0 --port 8001 --reload \
  --reload-exclude "model_registry/*" --reload-exclude "uploads/*" --reload-exclude "ycsb_runs.json"
```

Verify: http://localhost:8001/api/v1/health → `{"status":"ok", ...}` · API docs: http://localhost:8001/docs

## 4. Frontend

`frontend/.env` (already present): `REACT_APP_BACKEND_URL=http://localhost:8001`

```bash
cd frontend
yarn install
yarn start
```

Dashboard: http://localhost:3000

## 5. Verify it works

1. Dashboard loads at :3000 with the dark sidebar (Overview … Demo Mode).
2. Click **Start Demo** (topbar) or **Demo Mode → Start Demo** — cluster starts simulating, `t_sim` advances, KPI cards populate.
3. **Model Training → Train** (GRU) returns measured F1/AUC + loss curves; model appears in **Model Comparison** and survives a backend restart (`backend/model_registry/`).
4. **Workload Lab**: upload a telemetry CSV (15 documented columns, ≥120 rows) → select `csv:<name>` in Model Training → train.
5. Optional YCSB: `GET /api/v1/ycsb/validate` shows REAL YCSB when configured.

## 6. Tests

```bash
cd backend && pip install pytest pytest-xdist
python -m pytest ../tests -q            # pipeline / YCSB / CSV / persistence unit+integration
python -m pytest tests -n 0             # live API tests (backend must be running; serial)
```
