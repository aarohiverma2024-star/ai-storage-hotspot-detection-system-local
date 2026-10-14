# CHANGELOG — Standalone Platform Cleanup

All changes in this release are platform-cleanup only. No application functionality, UI design, API behavior, ML logic, database logic, or folder structure was intentionally changed.

## Removed (platform-specific only)
- `.emergent/` platform metadata directory
- Git history and `.gitconfig` containing platform identity
- Platform test-agent registry `frontend/src/constants/testIds/` (unused by any application component)
- Platform preview health-check plugin `frontend/plugins/health-check/` and its craco wiring
- Platform visual-editing devDependency `@emergentbase/visual-edits` from `frontend/package.json`
- Platform-only backend dependencies from `backend/requirements.txt` (`emergentintegrations`, platform-hosted `litellm` wheel URL) — not imported by any application code
- Platform process docs/artifacts: `test_result.md`, `test_reports/`, `memory/`, `design_guidelines.json`, empty root `yarn.lock`
- Runtime artifacts from the repo: trained model weights (`backend/model_registry/*`), uploaded CSVs (`backend/uploads/*`), `backend/ycsb_runs.json` — all regenerated locally at runtime

## Modified (platform-reference removal only)
- `frontend/public/index.html` — removed platform meta description, platform analytics script, and platform page title; now titled "Predictive Storage Guardian"
- `frontend/craco.config.js` — removed visual-edits wrapper and preview health-check wiring; dev-server compatibility shim retained
- `frontend/.env` — `REACT_APP_BACKEND_URL=http://localhost:8001`; removed preview-socket variables
- `backend/tests/backend_test.py`, `backend/tests/test_new_features.py` — default test base URL changed from the preview URL to `http://localhost:8001`
- `docs/DEPLOYMENT.md` — replaced platform-container section with generic VS Code/local instructions
- `.gitignore` — added runtime artifacts (model registry, uploads, YCSB run log)

## Added
- `CHANGELOG.md` (this file)
- `LOCAL_DEVELOPMENT.md` — VS Code run instructions
- `GITHUB_GUIDE.md` — repository push guide
