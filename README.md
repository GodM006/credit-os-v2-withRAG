# Credit Decisioning OS

Agentic credit underwriting backend + console UI. 6 layers: LLM extraction (with RAG) → graph context (Neo4j) → reconciliation/fraud detection → policy rules → ML risk scoring → sanction memo.

## Stack
- Backend: FastAPI (Python), Neo4j, Groq LLM API, LightGBM (risk model)
- Frontend: React + Vite

## Setup

### 0. Prereqs
- Node.js LTS
- Free Groq API key → https://console.groq.com
- Neo4j running locally, reachable at `http://localhost:7474`

### 1. Backend
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env   # fill GROQ_API_KEY and NEO4J_PASSWORD
```

### 2. Pretrained ML model
`app/ml/risk_model.joblib` is already **pretrained on synthetic data** — the app works out of the box, no training step needed.

Only retrain if you're swapping in real data:
```powershell
python -m app.ml.train_model --retrain
```
Without `--retrain`, running `python -m app.ml.train_model` just re-uses/regenerates the cached synthetic model. To use your own dataset, replace the data-generation logic in `app/ml/trainer.py` (or point it at your real data) and run `--retrain` — this overwrites `risk_model.joblib`. Delete that file manually if you ever want to force a clean rebuild.

### 3. Start backend
```powershell
uvicorn app.main:app --reload --port 8000
```
Check: `http://localhost:8000` → `{"status":"ok", ...}`
Check Neo4j link: `http://localhost:8000/api/layer2/health` → `{"neo4j_reachable": true}`

### 4. Frontend
```powershell
cd frontend
npm install
npm run dev
```
Open `http://localhost:5173`

## Using the app
1. Pick a scenario (Clean / Fraud-risk / Noisy OCR) → **Generate case**
2. Run Layer 1 → 6 in order. Each button lights up the pipeline as agents/graph/rules/model complete.
3. **Generate linked pair** — for the related-party fraud demo (two cases sharing a director/bank account). Run Layers 1–3 on both cases to see `related_party_exposure` and `shared_banking_instrument` fraud signals.

## Troubleshooting
| Symptom | Fix |
|---|---|
| `ModuleNotFoundError` on server start | venv not activated |
| `neo4j_reachable: false` | wrong password/URI in `.env`, or Neo4j not running |
| Layer 1 agents all `invalid` | bad/expired Groq key or quota hit |
| Groq `model not found` | model deprecated — check `console.groq.com/docs/models`, update `GROQ_MODEL` in `.env` |
| Port 8000 busy | run uvicorn on `--port 8001`, update `CORS_ORIGINS` in `.env` |

Both servers hot-reload on file changes — no restart needed while developing.