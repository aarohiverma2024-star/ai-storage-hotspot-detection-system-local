# Deployment

## Local development (VS Code)

Two processes, no platform dependencies:

```bash
# Terminal 1 — backend (FastAPI on :8001)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install --index-url https://download.pytorch.org/whl/cpu torch==2.4.1
uvicorn server:app --host 0.0.0.0 --port 8001 --reload \
  --reload-exclude "model_registry/*" --reload-exclude "uploads/*" \
  --reload-exclude "ycsb_runs.json"

# Terminal 2 — frontend (React on :3000)
cd frontend
yarn install
yarn start
```

Env: `backend/.env` (`MONGO_URL`, `DB_NAME`, `CORS_ORIGINS`), `frontend/.env` (`REACT_APP_BACKEND_URL`). See `.env.example` files.

## Docker

```bash
docker compose up --build
# frontend http://localhost:3000 · backend http://localhost:8001/docs · mongo :27017
```

Services: `frontend` (React build → nginx), `backend` (FastAPI/uvicorn), `mongo`. No secrets are baked in; use `.env` (see `.env.example`).

## Optional: official YCSB

Install Java 17+ and the official YCSB release, then point `YCSB_HOME` at it (default lookup: `/opt/ycsb`). `GET /api/v1/ycsb/validate` performs real detection. Without it, the app honestly reports `YCSB NOT CONFIGURED` and runs in synthetic simulation mode.

## Production notes

- Set `CORS_ORIGINS` to your domain; never `*`.
- Run the backend with a process manager (systemd/supervisor); the simulator loop runs inside the backend process.
- Persisted model artifacts live in `backend/model_registry/` (git-ignored runtime data).
