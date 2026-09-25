# DevProof AI — MVP Implementation Plan

## Top-Level Overview

**Goal:** Build a 48-hour hackathon MVP of DevProof AI — an AI-powered developer workflow assistant
that takes a bug description + relevant source files as input, identifies root causes, proposes
fixes, **waits for human approval**, then runs full automated verification and produces a report.

**Tagline:** "Don't just suggest a fix. Prove it works."

**Stack:** React + Vite (frontend) · Python + FastAPI (backend) · SQLite (persistence) · REST API

**LLM Strategy:** All AI calls go through a provider-agnostic `LLMProvider` abstraction.
The concrete provider (IBM watsonx, OpenAI, or other) is selected at runtime via environment
variable. No workflow code imports any provider SDK directly.

**Scope (MVP):**
- User selects a built-in sample project OR uploads individual `.py` source files
- User types a bug description
- AI performs analysis → root cause → fix suggestion
- **User reviews the proposed fix and approves or rejects it**
- On approval: AI generates tests → pytest runs → verification report produced
- All test execution is against a controlled backend workspace only

**Out of scope (post-hackathon):** GitHub/GitLab OAuth, real-time streaming, CI/CD integration,
full repository upload, Docker sandboxing, user accounts, JS/TS test execution.

---

## Multi-Step Workflow

```
User
 │
 ├─ 1. SELECT PROJECT  ─── sample project or upload .py files
 │
 ├─ 2. DESCRIBE BUG    ─── free-text bug description
 │
 ├─ 3. ANALYZE         ──► LLM: relevant files ranked by confidence
 │
 ├─ 4. ROOT CAUSE      ──► LLM: probable cause per file
 │
 ├─ 5. FIX PROPOSAL    ──► LLM: original → suggested code per file
 │
 ├─ 6. HUMAN APPROVAL  ─── user reviews diff, clicks Approve or Reject
 │                          (Reject → back to step 2 with feedback)
 │
 └─ 7. RUN FULL VERIFICATION  (triggered only after approval)
       │
       ├─ 7a. GENERATE TESTS  ──► LLM: pytest test code for each fix
       │
       ├─ 7b. RUN TESTS       ──► subprocess pytest on controlled workspace
       │
       └─ 7c. VERIFICATION REPORT ──► LLM: verdict + 2-3 sentence summary
```

---

## Architecture Overview

```
User Browser
    │
    ▼
React + Vite (port 5173)
    │  REST (JSON)
    ▼
FastAPI (port 8000)
    ├── /api/projects      — list sample projects, upload files
    ├── /api/sessions      — create / list / update sessions
    ├── /api/analysis      — file relevance + root cause       (LLMProvider)
    ├── /api/fix           — fix suggestions                   (LLMProvider)
    ├── /api/fix/{id}/approve  — human approval gate
    ├── /api/verify        — test gen + pytest + report        (LLMProvider)
    └── /api/report        — get verification report
    │
    ├── LLMProvider (abstraction)
    │     ├── WatsonxProvider    ← LLM_PROVIDER=watsonx
    │     ├── OpenAIProvider     ← LLM_PROVIDER=openai
    │     └── MockProvider       ← LLM_PROVIDER=mock  (offline dev)
    │
    ├── Controlled Workspace  backend/workspace/{session_id}/
    └── SQLite DB  (sessions, analyses, fix_suggestions, reports)
```

---

## LLM Provider Abstraction

```
backend/llm/
├── base.py               # LLMProvider ABC: complete(messages, json_mode) → str
├── watsonx.py            # WatsonxProvider
├── openai_provider.py    # OpenAIProvider
├── mock_provider.py      # MockProvider — hardcoded valid responses (no API key needed)
└── factory.py            # get_provider() reads LLM_PROVIDER env var
```

**Environment variables:**
```
LLM_PROVIDER=watsonx              # watsonx | openai | mock
LLM_MODEL=ibm/granite-13b-chat-v2 # model id string passed to provider

# watsonx credentials:
WATSONX_API_KEY=
WATSONX_PROJECT_ID=
WATSONX_URL=

# openai credentials (fallback/dev):
OPENAI_API_KEY=
```

**Provider interface:**
```python
class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: list[dict],  # [{"role": "system"|"user", "content": str}]
        json_mode: bool = False
    ) -> str: ...
```

---

## REST API Contract

This section is the source of truth for frontend-backend integration.
Both developers must not deviate from these shapes without updating this document first.

### Projects

| Method | Path | Request body | Response |
|---|---|---|---|
| GET | `/api/projects` | — | `Project[]` |
| GET | `/api/projects/{id}/files` | — | `ProjectFile[]` |
| POST | `/api/projects/upload` | `multipart/form-data files[]` | `UploadResult` |

```jsonc
// Project
{ "id": "order_service", "name": "Order Service", "description": "...", "file_count": 2 }

// ProjectFile
{ "path": "order_service.py", "description": "Core order logic" }

// UploadResult
{ "session_file_paths": ["order_service.py"] }
```

### Sessions

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | `/api/sessions` | `SessionCreate` | `Session` |
| GET | `/api/sessions` | — | `Session[]` |
| GET | `/api/sessions/{id}` | — | `Session` |

```jsonc
// SessionCreate
{ "project_id": "order_service", "bug_description": "Discount applied incorrectly..." }

// Session
{
  "id": "uuid",
  "project_id": "order_service",
  "project_name": "Order Service",
  "bug_description": "...",
  "status": "created",   // created | analyzed | fix_proposed | fix_approved | fix_rejected | verified
  "created_at": "ISO8601"
}
```

### Analysis

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | `/api/analysis` | `{ "session_id": "uuid" }` | `AnalysisResult` |
| GET | `/api/analysis/{session_id}` | — | `AnalysisResult` |

```jsonc
// AnalysisResult
{
  "session_id": "uuid",
  "relevant_files": [
    { "path": "order_service.py", "confidence": 0.94, "reason": "Discount logic is here" }
  ],
  "root_causes": [
    { "description": "Discount applied before tax, not after", "file": "order_service.py", "line_hint": 27 }
  ]
}
```

### Fix Suggestions

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | `/api/fix` | `{ "session_id": "uuid" }` | `FixList` |
| GET | `/api/fix/{session_id}` | — | `FixList` |
| POST | `/api/fix/{session_id}/approve` | `{ "approved": true \| false, "feedback": "..." }` | `{ "status": "fix_approved" \| "fix_rejected" }` |

```jsonc
// FixList
{
  "session_id": "uuid",
  "fixes": [
    {
      "id": "uuid",
      "file_path": "order_service.py",
      "original": "total = subtotal * (1 - discount)",
      "suggested": "total = (subtotal * tax_rate) * (1 - discount)",
      "explanation": "Tax must be applied before discount to match pricing rules."
    }
  ]
}
```

**Approval gate:** `POST /api/fix/{session_id}/approve` with `approved: true` transitions
`session.status` to `fix_approved`. `POST /api/verify` will reject with HTTP 409 if called
before approval.

### Verification (test gen + run + report — single orchestrated call)

| Method | Path | Request body | Response |
|---|---|---|---|
| POST | `/api/verify` | `{ "session_id": "uuid" }` | `VerificationReport` |
| GET | `/api/report/{session_id}` | — | `VerificationReport` |

```jsonc
// VerificationReport
{
  "session_id": "uuid",
  "project_name": "Order Service",
  "bug_description": "...",
  "verdict": "PASS",   // PASS | FAIL | PARTIAL | ERROR
  "relevant_files": [...],
  "root_causes": [...],
  "fixes": [...],
  "tests_generated": [{ "file": "test_order_service.py", "code": "..." }],
  "test_output": "3 passed in 0.21s",
  "tests_passed": 3,
  "tests_failed": 0,
  "summary": "The discount/tax ordering bug in order_service.py was corrected. All 3 generated tests pass.",
  "created_at": "ISO8601"
}
```

---

## Sub-Tasks

---

### Sub-Task 1 — Project Scaffold & Folder Structure

**Intent:** Establish the monorepo layout, dev server wiring, and health check so both
developers can work in parallel from hour one.

**Expected Outcomes:**
- `frontend/` and `backend/` directories exist with working dev servers
- Frontend reaches backend via `VITE_API_URL` env var
- Backend returns `GET /health`
- SQLite DB initialized on startup
- `README.md` covers full dev setup for both developers

**Todo List:**
1. Create root `devproof-ai/` with `frontend/` and `backend/` subdirectories
2. Scaffold frontend: `npm create vite@latest frontend -- --template react-ts`
3. Install frontend deps: `axios`, `react-router-dom`, `tailwindcss`
4. Scaffold backend: `python -m venv .venv`
5. Install backend deps: `fastapi`, `uvicorn`, `python-dotenv`, `ibm-watsonx-ai`, `openai`, `aiofiles`
6. Create `backend/main.py` with FastAPI app, CORS, lifespan, and `GET /health`
7. Add `.env.example` for both frontend and backend (see env vars above)
8. Create root `README.md` with `npm run dev` and `uvicorn backend.main:app --reload` commands
9. Add `.gitignore`: `node_modules/`, `__pycache__/`, `*.db`, `.env`, `.venv/`, `backend/workspace/`

**Status:** [ ] pending

---

### Sub-Task 2 — LLM Provider Abstraction

**Intent:** Build the provider-agnostic `LLMProvider` layer so every AI call in the codebase
goes through one interface. Workflow code never imports a provider SDK directly.

**Expected Outcomes:**
- `backend/llm/base.py` defines `LLMProvider` ABC with `complete()` signature
- `WatsonxProvider`, `OpenAIProvider`, and `MockProvider` all implement it
- `factory.py` selects provider from `LLM_PROVIDER` env var
- Provider instantiated once in FastAPI lifespan, injected via `app.state.llm`
- `MockProvider` returns deterministic valid responses for offline development

**Todo List:**
1. Create `backend/llm/base.py` — `LLMProvider` ABC (see interface above)
2. Create `backend/llm/watsonx.py` — `WatsonxProvider` using `ibm-watsonx-ai` SDK
3. Create `backend/llm/openai_provider.py` — `OpenAIProvider` using `openai` SDK
4. Create `backend/llm/mock_provider.py` — `MockProvider` with per-endpoint hardcoded JSON
5. Create `backend/llm/factory.py` — `get_provider()` → raises `ValueError` on unknown provider
6. Instantiate in `lifespan`; store as `app.state.llm`
7. All service functions accept `llm: LLMProvider` as an injected parameter

**Status:** [ ] pending

---

### Sub-Task 3 — Sample Projects & File Workspace

**Intent:** Supply the two controlled demo projects and the per-session workspace logic.
These are the only codebases pytest ever touches.

**Expected Outcomes:**
- `backend/sample_projects/order_service/` — deterministic discount/tax order bug
- `backend/sample_projects/auth_service/` — expired-token validation bug
- Each project has a `project.json` manifest
- `POST /api/projects/upload` accepts `.py` files into a session workspace
- `GET /api/projects` and `GET /api/projects/{id}/files` serve manifests

**Sample project specifications:**

**`order_service`** — `order_service.py`
- Bug: discount is applied to the pre-tax subtotal instead of the post-tax total
- Demonstrates a deterministic calculation error with clear numeric test cases
- Correct formula: `total = round(subtotal * tax_rate * (1 - discount_rate), 2)`
- Buggy formula: `total = round(subtotal * (1 - discount_rate) * tax_rate, 2)`
  (these produce identical results — use a more clearly wrong formula during implementation:
  `total = round((subtotal - discount_amount) * tax_rate, 2)` where `discount_amount`
  is computed on subtotal but should be computed on `subtotal * tax_rate`)
- `project.json`: `{ "id": "order_service", "name": "Order Service", "description": "E-commerce order total calculation with discount and tax handling.", "files": [{"path": "order_service.py", "description": "Order total, discount, and tax logic"}] }`

**`auth_service`** — `auth.py`
- Bug: token expiry check uses `>=` instead of `>`, so a token expiring exactly at the
  current timestamp is incorrectly accepted as valid
- Demonstrates an off-by-one logic error with deterministic time-based test cases
- `project.json`: `{ "id": "auth_service", "name": "Auth Service", "description": "Token-based authentication with expiry validation.", "files": [{"path": "auth.py", "description": "Token creation, validation, and expiry logic"}] }`

**Todo List:**
1. Create `backend/sample_projects/order_service/order_service.py` with the discount bug
2. Create `backend/sample_projects/order_service/project.json`
3. Create `backend/sample_projects/auth_service/auth.py` with the expiry bug
4. Create `backend/sample_projects/auth_service/project.json`
5. Create `backend/services/project_service.py` — `list_projects()`, `get_project_files(id)`, `create_workspace(session_id, project_id)`
6. Create `backend/routers/projects.py` — all three endpoints
7. Enforce upload constraints: `.py` only, max 5 files, max 100KB per file
8. Register router in `main.py`

**Status:** [ ] pending

---

### Sub-Task 4 — Data Models & SQLite Schema

**Intent:** Define the shared schema and Pydantic models so both developers have a stable
API contract from the start.

**Expected Outcomes:**
- `backend/db/schema.sql` defines all tables including `fix_approvals`
- `backend/models/` Pydantic schemas match the REST API contract exactly
- Schema initialized on FastAPI startup

**Todo List:**
1. Create `backend/db/schema.sql` with tables below
2. Create `backend/db/database.py` — `get_db()` context manager (`sqlite3`)
3. Create `backend/models/session.py` — `Session`, `SessionCreate`, `SessionStatus` enum
4. Create `backend/models/analysis.py` — `AnalysisResult`, `FileRelevance`, `RootCause`
5. Create `backend/models/fix.py` — `FixSuggestion`, `FixList`, `FixApproval`
6. Create `backend/models/report.py` — `VerificationReport`
7. Wire `init_db()` into FastAPI `lifespan`

**Schema:**
```sql
sessions
  id              TEXT PRIMARY KEY
  created_at      DATETIME
  project_id      TEXT
  project_name    TEXT
  bug_description TEXT
  status          TEXT  -- created | analyzed | fix_proposed | fix_approved | fix_rejected | verified

analyses
  id              TEXT PRIMARY KEY
  session_id      TEXT REFERENCES sessions(id)
  relevant_files  TEXT  -- JSON: FileRelevance[]
  root_causes     TEXT  -- JSON: RootCause[]
  created_at      DATETIME

fix_suggestions
  id              TEXT PRIMARY KEY
  session_id      TEXT REFERENCES sessions(id)
  file_path       TEXT
  original        TEXT
  suggested       TEXT
  explanation     TEXT
  created_at      DATETIME

fix_approvals
  id              TEXT PRIMARY KEY
  session_id      TEXT REFERENCES sessions(id)
  approved        INTEGER  -- 1 = approved, 0 = rejected
  feedback        TEXT     -- optional rejection reason
  created_at      DATETIME

reports
  id              TEXT PRIMARY KEY
  session_id      TEXT REFERENCES sessions(id)
  tests_generated TEXT     -- JSON: {file, code}[]
  test_output     TEXT     -- raw pytest stdout+stderr
  tests_passed    INTEGER
  tests_failed    INTEGER
  verdict         TEXT     -- PASS | FAIL | PARTIAL | ERROR
  summary         TEXT
  created_at      DATETIME
```

**Status:** [ ] pending

---

### Sub-Task 5 — Analysis & Root-Cause Service (Backend)

**Intent:** Implement the AI step that reads the bug description + file contents and returns
ranked relevant files with root causes.

**Expected Outcomes:**
- `POST /api/analysis` accepts `session_id`, reads workspace files, returns `AnalysisResult`
- Session status updated to `analyzed`
- All LLM calls use `llm.complete()` — no direct SDK calls

**Todo List:**
1. Create `backend/services/analysis_service.py`
2. `analyze(session_id, bug_description, file_contents, llm) -> AnalysisResult`
3. System prompt: expert code reviewer, respond in JSON only
4. User prompt: bug description + file contents (truncated to context limit)
5. `llm.complete(messages, json_mode=True)` → parse into `AnalysisResult`
6. Persist to `analyses` table; update `sessions.status = 'analyzed'`
7. Create `backend/routers/analysis.py` — `POST /api/analysis`, `GET /api/analysis/{session_id}`
8. Register router in `main.py`

**LLM JSON contract:**
```json
{
  "relevant_files": [
    { "path": "order_service.py", "confidence": 0.94, "reason": "Discount logic is applied before tax" }
  ],
  "root_causes": [
    { "description": "Discount applied to pre-tax amount instead of post-tax total", "file": "order_service.py", "line_hint": 27 }
  ]
}
```

**Status:** [ ] pending

---

### Sub-Task 6 — Fix Suggestion Service (Backend)

**Intent:** For each high-confidence relevant file, produce a concrete original→suggested
code change with explanation.

**Expected Outcomes:**
- `POST /api/fix` returns `FixList` with one fix per file (confidence > 0.6)
- Session status updated to `fix_proposed`
- Fixes persisted to `fix_suggestions` table

**Todo List:**
1. Create `backend/services/fix_service.py`
2. `generate_fixes(session_id, analysis_result, file_contents, llm) -> list[FixSuggestion]`
3. Per file: prompt includes file content + root cause; `json_mode=True`
4. Persist fixes; update `sessions.status = 'fix_proposed'`
5. Create `backend/routers/fix.py` — `POST /api/fix`, `GET /api/fix/{session_id}`, `POST /api/fix/{session_id}/approve`
6. `approve` endpoint: write to `fix_approvals`; update session status to `fix_approved` or `fix_rejected`; return HTTP 409 if already approved/rejected
7. Register router in `main.py`

**LLM JSON contract:**
```json
{
  "fixes": [
    {
      "file_path": "order_service.py",
      "original": "total = round((subtotal - discount_amount) * tax_rate, 2)",
      "suggested": "total = round(subtotal * tax_rate * (1 - discount_rate), 2)",
      "explanation": "Discount must be applied as a rate on the post-tax amount, not as an amount on the pre-tax subtotal."
    }
  ]
}
```

**Status:** [ ] pending

---

### Sub-Task 7 — Verification Service: Test Generation + Execution + Report (Backend)

**Intent:** Implement `POST /api/verify` — the single orchestrated endpoint that generates
tests, runs pytest, and compiles the report. Only callable after fix approval.

**Expected Outcomes:**
- `POST /api/verify` returns HTTP 409 if `session.status != 'fix_approved'`
- Applies the suggested fix to the workspace source file(s)
- LLM generates pytest tests for the fix
- pytest runs in `backend/workspace/{session_id}/` with 30s timeout
- LLM generates a summary; verdict computed from test counts
- Session status updated to `verified`; full report persisted

**Todo List:**
1. Create `backend/services/test_service.py` — `generate_tests(session_id, fixes, llm) -> list[dict]`
   - Prompt: "Write pytest tests that verify this fix. Return valid Python code only."
   - Strip markdown code fences from LLM response
2. Create `backend/services/validation_service.py` — `run_tests(session_id, generated_tests) -> ValidationResult`
   - Apply fix: write `suggested` content to `workspace/{session_id}/{file_path}`
   - Write generated test file(s) into workspace
   - `subprocess.run(["python", "-m", "pytest", ".", "-v", "--tb=short"], cwd=workspace_dir, timeout=30, capture_output=True)`
   - Validate workspace path with `Path.resolve()` before use (path traversal guard)
   - Parse pytest summary line: extract `X passed`, `X failed`
   - Clean test files from workspace after run (leave source files)
3. Create `backend/services/report_service.py` — `compile_report(session_id, validation_result, tests, llm) -> VerificationReport`
   - Compute verdict: all pass → PASS; any fail → FAIL; mix → PARTIAL; subprocess error → ERROR
   - Summary prompt: "2-3 sentence summary of the fix and test results."
   - Persist to `reports`; update `sessions.status = 'verified'`
4. Create `backend/routers/verify.py` — `POST /api/verify` (orchestrates steps 1-3 in sequence)
5. Create `backend/routers/report.py` — `GET /api/report/{session_id}`
6. Register both routers in `main.py`

**Security constraints:**
- `cwd` always set to resolved `backend/workspace/{session_id}/` — never user-controlled
- Subprocess always uses list form, never `shell=True`
- Hard timeout of 30 seconds
- Path traversal guard: assert resolved path starts with `WORKSPACE_ROOT`

**Known MVP limitation:** Subprocess not container-isolated. Document in `README.md`.

**Status:** [ ] pending

---

### Sub-Task 8 — Error Handling & Startup Validation (Backend)

**Intent:** Prevent demo-breaking crashes and surface actionable error messages.

**Expected Outcomes:**
- All routes return `{ "error": "...", "detail": "..." }` on failure
- LLM errors → HTTP 503
- Missing approval → HTTP 409 with clear message
- Backend fails to start if required env vars are absent

**Todo List:**
1. Add global exception handler in `main.py` (unhandled → 500)
2. Add `HTTPException` handler for 404 (session not found) and 409 (approval gate)
3. Define `LLMServiceError` exception; wrap all `llm.complete()` calls; map to HTTP 503
4. On startup: validate `LLM_PROVIDER`, `LLM_MODEL`, and provider-specific keys; raise with clear message if missing
5. Subprocess timeout → return `{ "verdict": "ERROR", "test_output": "Test execution timed out after 30s" }`

**Status:** [ ] pending

---

### Sub-Task 9 — Security Hardening (Backend)

**Intent:** Address the critical security surface.

**Expected Outcomes:**
- No secrets in code or responses
- Subprocess constrained to controlled workspace
- CORS locked to localhost
- Upload validated

**Todo List:**
1. Secrets via `python-dotenv` only; never logged or returned in responses
2. CORS: `allow_origins=["http://localhost:5173"]` only
3. Subprocess: list form, `shell=False`, `timeout=30`, `cwd` validated
4. Path traversal guard in `validation_service.py`
5. Upload: `.py` only, max 5 files, 100KB each → HTTP 400 otherwise
6. `X-Content-Type-Options: nosniff` header in FastAPI middleware
7. Document subprocess limitation in `README.md`

**Status:** [ ] pending

---

### Sub-Task 10 — Frontend: Scaffold, Routing & API Client

**Intent:** Establish all React pages, routes, and typed API service files so Developer 1
can implement each page without waiting on the backend.

**Expected Outcomes:**
- All pages stubbed and routed
- Typed API client files match the REST API contract exactly
- Tailwind CSS working

**Page Map:**

| Route | Page | Workflow Step |
|---|---|---|
| `/` | `DashboardPage` | Session history + "New Analysis" CTA |
| `/analysis/new` | `NewAnalysisPage` | Steps 1–2: project/file select + bug description |
| `/analysis/:id/results` | `AnalysisResultPage` | Steps 3–4: relevant files + root causes |
| `/analysis/:id/fix` | `FixSuggestionPage` | Step 5: diff view + Approve / Reject |
| `/analysis/:id/verify` | `VerificationPage` | Steps 7a–7b: test code + run output (post-approval) |
| `/analysis/:id/report` | `ReportPage` | Step 7c: verdict + summary report card |

**Todo List:**
1. Install and configure Tailwind CSS
2. Create `frontend/src/router.tsx` — `createBrowserRouter` with all routes above
3. Create `frontend/src/components/Layout.tsx` — top nav: logo, "New Analysis", "History"
4. Create page stubs for all six pages
5. `frontend/src/api/client.ts` — axios instance + `VITE_API_URL` + error interceptor
6. `frontend/src/api/projectsApi.ts` — `listProjects()`, `getProjectFiles(id)`, `uploadFiles(files)`
7. `frontend/src/api/sessionsApi.ts` — `createSession(body)`, `listSessions()`, `getSession(id)`
8. `frontend/src/api/analysisApi.ts` — `runAnalysis(session_id)`, `getAnalysis(session_id)`
9. `frontend/src/api/fixApi.ts` — `generateFixes(session_id)`, `getFixes(session_id)`, `approveFix(session_id, approved, feedback?)`
10. `frontend/src/api/verifyApi.ts` — `runVerification(session_id)`
11. `frontend/src/api/reportApi.ts` — `getReport(session_id)`

**Status:** [ ] pending

---

### Sub-Task 11 — Frontend: NewAnalysisPage

**Intent:** Entry point — project/file selection and bug description form.

**Expected Outcomes:**
- User picks a sample project OR uploads `.py` files (max 5)
- Bug description textarea with character count (min 20 chars)
- Submit calls `createSession()` then `runAnalysis()`, navigates to `/analysis/:id/results`

**Todo List:**
1. `ProjectSelector` component: fetch `GET /api/projects`, render name+description cards
2. `FileUpload` component: `<input type="file" multiple accept=".py">`, show file list
3. Bug description textarea with live char count
4. Submit: `createSession()` → `runAnalysis()` → navigate; show spinner during load
5. Inline validation: project or files required; bug description required

**Status:** [ ] pending

---

### Sub-Task 12 — Frontend: AnalysisResultPage & FixSuggestionPage

**Intent:** Display AI analysis and the fix proposal with human-approval controls.

**Expected Outcomes:**
- `AnalysisResultPage`: relevant file cards with confidence bars + root cause cards + "Suggest Fix →" CTA
- `FixSuggestionPage`: diff view per fix + explanation + **Approve** and **Reject** buttons
- On Approve: calls `POST /api/fix/{id}/approve` with `approved: true`, navigates to `/analysis/:id/verify`
- On Reject: calls `POST /api/fix/{id}/approve` with `approved: false` + optional feedback textarea, navigates back to `/analysis/new`

**Todo List:**
1. `FileRelevanceCard`: filename, confidence bar (0–100%), reason text
2. `RootCauseCard`: description, filename badge, line hint badge
3. `AnalysisResultPage`: fetch analysis on mount; render cards; "Suggest Fix →" CTA
4. `DiffViewer`: two `<pre>` columns (original / suggested); `+` lines green, `-` lines red
5. `FixSuggestionPage`: fetch fixes; render `DiffViewer` + explanation per fix
6. Approval row: **Approve Fix** (green) and **Reject** (red) buttons; rejection shows feedback textarea
7. Both buttons call `approveFix()`, then navigate accordingly

**Status:** [ ] pending

---

### Sub-Task 13 — Frontend: VerificationPage & ReportPage

**Intent:** Show the full automated verification run and the final report.

**Expected Outcomes:**
- `VerificationPage`: "Run Full Verification" button triggers `POST /api/verify`; shows generated test code + terminal output
- `ReportPage`: verdict badge, summary, collapsible sections for each workflow step

**Todo List:**
1. `CodeBlock`: `<pre><code>` monospace, copy button
2. `TerminalOutput`: dark bg, monospace, scrollable, raw pytest stdout
3. `VerificationPage`: "Run Full Verification" CTA; on result show test code + terminal output + pass/fail counts; "View Report →" CTA
4. `VerdictBadge`: `PASS`=green, `FAIL`=red, `PARTIAL`=yellow, `ERROR`=orange
5. `ReportPage`: fetch report; `VerdictBadge`, summary paragraph, collapsible sections (files / root causes / fixes / tests)
6. "Copy Report JSON" button: `navigator.clipboard.writeText(JSON.stringify(report, null, 2))`
7. "New Analysis" button → `/analysis/new`

**Status:** [ ] pending

---

### Sub-Task 14 — Frontend: Error Handling & Polish

**Intent:** Prevent demo failures from reaching the user as raw JSON.

**Expected Outcomes:**
- All API errors shown as toast notifications
- LLM errors show "AI service unavailable — please retry"
- Approval-gate errors show "Fix must be approved before running verification"

**Todo List:**
1. `axios` response interceptor: extract `error` field, emit toast
2. `Toast.tsx` component: error (red), success (green), auto-dismiss after 4s
3. Loading spinners on all async CTA buttons
4. Handle HTTP 409 from `/api/verify` with specific "approval required" message

**Status:** [ ] pending

---

## Folder Structure

```
devproof-ai/
├── README.md
├── .gitignore
│
├── frontend/                               # Developer 1
│   ├── index.html
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── .env.example
│   └── src/
│       ├── main.tsx
│       ├── router.tsx
│       ├── api/
│       │   ├── client.ts
│       │   ├── projectsApi.ts
│       │   ├── sessionsApi.ts
│       │   ├── analysisApi.ts
│       │   ├── fixApi.ts
│       │   ├── verifyApi.ts
│       │   └── reportApi.ts
│       ├── components/
│       │   ├── Layout.tsx
│       │   ├── Toast.tsx
│       │   ├── ProjectSelector.tsx
│       │   ├── FileUpload.tsx
│       │   ├── FileRelevanceCard.tsx
│       │   ├── RootCauseCard.tsx
│       │   ├── DiffViewer.tsx
│       │   ├── CodeBlock.tsx
│       │   ├── TerminalOutput.tsx
│       │   └── VerdictBadge.tsx
│       └── pages/
│           ├── DashboardPage.tsx
│           ├── NewAnalysisPage.tsx
│           ├── AnalysisResultPage.tsx
│           ├── FixSuggestionPage.tsx
│           ├── VerificationPage.tsx
│           └── ReportPage.tsx
│
└── backend/                                # Developer 2
    ├── main.py
    ├── requirements.txt
    ├── .env.example
    ├── data/                               # gitignored
    │   └── devproof.db
    ├── workspace/                          # gitignored
    │   └── {session_id}/
    ├── sample_projects/                    # committed
    │   ├── order_service/
    │   │   ├── project.json
    │   │   └── order_service.py
    │   └── auth_service/
    │       ├── project.json
    │       └── auth.py
    ├── llm/
    │   ├── base.py
    │   ├── factory.py
    │   ├── watsonx.py
    │   ├── openai_provider.py
    │   └── mock_provider.py
    ├── db/
    │   ├── schema.sql
    │   ├── database.py
    │   └── init.py
    ├── models/
    │   ├── session.py
    │   ├── analysis.py
    │   ├── fix.py
    │   └── report.py
    ├── routers/
    │   ├── projects.py
    │   ├── sessions.py
    │   ├── analysis.py
    │   ├── fix.py
    │   ├── verify.py
    │   └── report.py
    └── services/
        ├── project_service.py
        ├── analysis_service.py
        ├── fix_service.py
        ├── test_service.py
        ├── validation_service.py
        └── report_service.py
```

---

## Git Workflow

```
main              ← stable, demo-ready at all times
  dev/frontend    ← Developer 1 (React)
  dev/backend     ← Developer 2 (FastAPI)
```

- Never commit to `main` directly
- Merge to `main` only when both sides of a feature work together
- Merge `main` → your branch before each new block
- Commit prefix: `feat:`, `fix:`, `chore:`

**Suggested checkpoints:**
- Hour 8:  Scaffold + LLM abstraction + sample projects on `main`
- Hour 16: Analysis + fix + approval endpoints; frontend input + results pages stubbed on `main`
- Hour 32: Full workflow (analyze → approve → verify → report) functional end-to-end
- Hour 40: Both sample projects demoed; error handling; polish
- Hour 48: Freeze, record demo

---

## MVP Essential Features

1. Sample project selection (order_service, auth_service)
2. Individual `.py` file upload (up to 5)
3. Bug description input
4. LLM analysis: relevant files ranked by confidence
5. LLM root-cause identification
6. LLM fix suggestions with diff view
7. **Human approval gate** before verification runs
8. "Run Full Verification" — test gen + pytest + report in one action
9. Controlled pytest execution (workspace-only)
10. Verification report with verdict badge and LLM summary
11. Session history on dashboard
12. LLM provider abstraction (watsonx / openai / mock via env var)

---

## Features to Leave for Later

- GitHub/GitLab OAuth and live repository cloning
- Full repository zip upload
- Real-time LLM streaming (WebSockets / SSE)
- Docker/container-based test sandboxing
- JavaScript/TypeScript test execution
- Applying fixes back to source files permanently
- Multi-user sessions and authentication
- Shareable public report URLs
- CI/CD webhook integration
- Token usage / cost tracking per session
- Embedding-based semantic search for large codebases
