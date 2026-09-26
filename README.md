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

## Security (ST-9)

### Upload Restrictions

The `POST /api/projects/upload` endpoint enforces the following restrictions:

| Constraint | Value | HTTP status on violation |
|---|---|---|
| Allowed file types | `.py` only | 400 Bad Request |
| Maximum files per upload | 5 | 400 Bad Request |
| Maximum file size | 100 KB per file | 400 Bad Request |
| Path-traversal filenames | Rejected (e.g. `../evil.py`, `sub/dir.py`) | 400 Bad Request |

Uploaded files are saved under `backend/workspace/{session_id}/` using the
bare filename only. No directory components from the client filename are
ever used.

### Test Execution Model

Uploaded source files and LLM-generated test files are executed **only**
through a controlled pytest subprocess:

- Subprocess uses list-form command, `shell=False`, `cwd` fixed to the
  validated session workspace directory.
- A hard 30-second timeout is enforced. Timed-out runs return verdict `ERROR`.
- Only `.py` files may be written into the workspace.
- The workspace path is always derived from a trusted root, never from
  user-supplied input.
- **Arbitrary uploaded code is not executed directly.** pytest is invoked
  by the backend on LLM-generated test code; the uploaded source files are
  only imported by those tests.

### CORS Policy

Allowed origins are configured via the `CORS_ORIGINS` environment variable
(comma-separated). The wildcard `*` is never used. The default value
covers the local Vite dev server (`http://localhost:5173`).

### Response Headers

All API responses include `X-Content-Type-Options: nosniff`.

### Error Responses

All error responses follow the standard envelope:

```json
{ "error": "<short label>", "detail": "<message>" }
```

Stack traces, secrets, credentials, and internal filesystem paths are
never included in API responses.

### Known MVP Security Limitations

- No authentication or authorisation: all API endpoints are publicly
  accessible. This is intentional for the MVP.
- No rate limiting on upload or LLM endpoints.
- Sessions and their workspaces persist until manually cleaned up.
- pytest subprocess executes LLM-generated code inside the server process
  user's environment; container/sandbox isolation is not implemented at the
  MVP stage.
- CORS credentials flag is enabled; in production, `CORS_ORIGINS` must be
  set to the exact deployed frontend URL.

---

## Sub-Task Progress

| Sub-Task | Description | Status |
|---|---|---|
| ST-1 | Project Scaffold & Folder Structure | ✅ Done |
| ST-2 | LLM Provider Abstraction | ✅ Done |
| ST-3 | Sample Projects & File Workspace | ✅ Done |
| ST-4 | Data Models & SQLite Schema | ✅ Done |
| ST-5 | Analysis & Root-Cause Service | ✅ Done |
| ST-6 | Fix Suggestion Service | ✅ Done |
| ST-7 | Verification Service | ✅ Done |
| ST-8 | Error Handling & Startup Validation | ✅ Done |
| ST-9 | Security Hardening | ✅ Done |
