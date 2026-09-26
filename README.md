# DevProof AI

> **"Don't just suggest a fix. Prove it works."**

AI-powered developer workflow assistant — identifies root causes, proposes fixes, waits for human approval, then runs full automated verification and produces a report.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Backend | Python 3.11+ · FastAPI · SQLite |
| LLM | IBM watsonx / OpenAI / Mock (provider-agnostic) |

---

## Quick Start

### Prerequisites

- Node.js 20+
- Python 3.11+

---

### Backend

```bash
cd backend

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env — set LLM_PROVIDER=mock for offline development

# Run development server
uvicorn main:app --reload --port 8000
```

Backend will be available at <http://localhost:8000>

Health check: <http://localhost:8000/health>

API docs (auto-generated): <http://localhost:8000/docs>

---

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env
# VITE_API_URL should be http://localhost:8000

# Run development server
npm run dev
```

Frontend will be available at <http://localhost:5173>

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|---|---|---|
| `CORS_ORIGINS` | `http://localhost:5173` | Allowed frontend origins (comma-separated) |
| `LLM_PROVIDER` | `mock` | `mock` · `watsonx` · `openai` |
| `LLM_MODEL` | `ibm/granite-13b-chat-v2` | Model ID passed to provider |
| `WATSONX_API_KEY` | — | Required when `LLM_PROVIDER=watsonx` |
| `WATSONX_PROJECT_ID` | — | Required when `LLM_PROVIDER=watsonx` |
| `WATSONX_URL` | — | Required when `LLM_PROVIDER=watsonx` |
| `OPENAI_API_KEY` | — | Required when `LLM_PROVIDER=openai` |

### Frontend (`frontend/.env`)

| Variable | Default | Description |
|---|---|---|
| `VITE_API_URL` | `http://localhost:8000` | Backend base URL |

---

## Project Structure

```
devproof-ai/
├── README.md
├── .gitignore
├── frontend/               # Developer 1 — React + Vite
└── backend/                # Developer 2 — FastAPI
    ├── main.py             # App entry point, CORS, health endpoint
    ├── requirements.txt
    ├── .env.example
    ├── data/               # gitignored — SQLite DB
    ├── workspace/          # gitignored — per-session file workspace
    ├── sample_projects/    # committed — built-in sample projects
    ├── db/                 # Database connection + schema
    ├── llm/                # LLM provider abstraction (ST-2)
    ├── models/             # Pydantic data models (ST-4)
    ├── routers/            # FastAPI routers (ST-3+)
    └── services/           # Business logic services (ST-3+)
```

---

## Sub-Task Progress

| Sub-Task | Description | Status |
|---|---|---|
| ST-1 | Project Scaffold & Folder Structure | ✅ Done |
| ST-2 | LLM Provider Abstraction | ⬜ Pending |
| ST-3 | Sample Projects & File Workspace | ⬜ Pending |
| ST-4 | Data Models & SQLite Schema | ⬜ Pending |
| ST-5 | Analysis & Root-Cause Service | ⬜ Pending |
| ST-6 | Fix Suggestion Service | ⬜ Pending |
| ST-7 | Verification Service | ⬜ Pending |
| ST-8 | Error Handling & Startup Validation | ⬜ Pending |
| ST-9 | Security Hardening | ⬜ Pending |
