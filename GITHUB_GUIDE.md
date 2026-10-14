# Pushing to GitHub

The included `.gitignore` already excludes: `.env*`, `node_modules/`, `build/`, `__pycache__/`, venvs, and runtime artifacts (`backend/model_registry/*`, `backend/uploads/*`, `backend/ycsb_runs.json`). Trained weights and uploaded datasets are regenerated locally — do not commit them.

```bash
cd Predictive-Storage-Guardian

git init
git add .
git status                       # confirm no .env, weights, or uploads are staged
git commit -m "Predictive Storage Guardian: predictive storage hotspot detection and cross-layer mitigation"

git branch -M main
git remote add origin https://github.com/<your-username>/predictive-storage-guardian.git
git push -u origin main
```

## If a secret was ever committed

Rotate it, then purge history (e.g. `git filter-repo --path backend/.env --invert-paths`) before pushing. The bundled `.env` files contain only localhost placeholders — no keys — but always re-check with `git status` / `git diff --cached`.

## Suggested repo description

> AI-based predictive storage hotspot detection & cross-layer mitigation. GRU/LSTM forecasting over YCSB-compatible workloads on a simulated distributed storage cluster. FastAPI + PyTorch + scikit-learn + React. Extends KML (Akgun et al.) observe-and-tune from reactive to predictive control.
