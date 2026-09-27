# DevProof AI

> **Don't just suggest a fix. Prove it works.**

DevProof AI is an AI-powered developer workflow assistant that helps developers go from **bug report → root cause → proposed fix → human approval → automated verification → proof**.

Instead of stopping after suggesting a code change, DevProof AI generates tests, runs them against the controlled project workspace, and produces a verification report showing whether the proposed fix actually works.

---

## 🚀 The Problem

AI coding assistants can suggest fixes quickly, but a suggested fix is not necessarily a correct fix.

Developers still need to:

* Find the relevant files
* Understand the root cause
* Review the proposed change
* Write tests
* Run the tests
* Determine whether the fix actually solved the reported problem
* Communicate the result

DevProof AI brings these steps into one verification-focused workflow.

---

## 💡 The Solution

DevProof AI analyzes a reported bug and guides the developer through a controlled workflow:

```text
Bug Description
      ↓
Project / Source Files
      ↓
AI Analysis
      ↓
Relevant Files + Root Cause
      ↓
Fix Proposal
      ↓
Human Approval
      ↓
AI-Generated Tests
      ↓
pytest Execution
      ↓
Verification Report
```

The developer remains in control: **AI proposes, the developer approves, and automated tests provide the proof.**

---

## ✨ Key Features

### 🔍 AI Code Analysis

Identifies relevant files and explains the probable root cause of the reported issue.

### 🛠️ Fix Suggestions

Shows the original code, suggested replacement, and explanation of the proposed fix.

### 👤 Human Approval Gate

A developer must explicitly approve the proposed fix before verification begins.

### 🧪 Automated Test Generation

Generates targeted pytest tests designed to validate the proposed behavior.

### ▶️ Controlled Test Execution

Runs the generated tests against a controlled backend workspace.

### 📊 Verification Report

Produces a final report containing:

* Verdict
* Tests passed / failed
* Generated tests
* Test output
* Relevant files
* Root cause
* Fix explanation
* Verification summary

### 🔌 Provider-Agnostic AI

The backend uses an `LLMProvider` abstraction so the workflow is not tightly coupled to a single AI provider.

Supported provider implementations:

* IBM watsonx
* OpenAI
* Mock provider for offline development

---

## 🎯 Example

DevProof AI's sample Order Service contains a coupon calculation bug.

### Buggy behavior

```python
total = round((subtotal - coupon_discount) * tax_rate, 2)
```

The coupon is applied before tax.

### Proposed fix

```python
total = round(subtotal * tax_rate - coupon_discount, 2)
```

The coupon is applied after tax.

For:

```text
subtotal = 100
tax_rate = 1.1
coupon_discount = 10
```

The buggy calculation produces:

```text
99.0
```

The corrected calculation produces:

```text
100.0
```

DevProof AI generates tests that distinguish these two behaviors and executes them with pytest.

Example verification result:

```text
PASS

3 tests passed
3/3 tests passed

✓ Coupon applied after tax
✓ No coupon
✓ Large coupon

Fix verified
```

---

## 🏗️ Architecture

```text
                    ┌──────────────────┐
                    │   React + Vite   │
                    │    Frontend      │
                    └────────┬─────────┘
                             │ REST / JSON
                             ▼
                    ┌──────────────────┐
                    │     FastAPI      │
                    │     Backend      │
                    └────────┬─────────┘
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
        ┌──────────┐   ┌──────────┐   ┌──────────┐
        │ Analysis │   │   Fix    │   │  Verify  │
        │ Service  │   │ Service  │   │ Service  │
        └────┬─────┘   └────┬─────┘   └────┬─────┘
             │              │              │
             └──────────────┼──────────────┘
                            ▼
                    ┌──────────────────┐
                    │  LLM Provider    │
                    │   Abstraction    │
                    └────────┬─────────┘
                             │
                ┌────────────┼────────────┐
                ▼            ▼            ▼
            watsonx        OpenAI       Mock
                             │
                             ▼
                    ┌──────────────────┐
                    │ Controlled       │
                    │ Workspace        │
                    └────────┬─────────┘
                             ▼
                         pytest
                             │
                             ▼
                    Verification Report
```

---

## 🧰 Tech Stack

| Layer       | Technology                               |
| ----------- | ---------------------------------------- |
| Frontend    | React 18, Vite, TypeScript, Tailwind CSS |
| Backend     | Python 3.11+, FastAPI                    |
| Database    | SQLite                                   |
| API         | REST / JSON                              |
| Testing     | pytest                                   |
| AI          | IBM watsonx / OpenAI / Mock provider     |
| Persistence | SQLite                                   |
| Development | IBM Bob 2.0                              |

---

## 🤖 IBM Bob 2.0

IBM Bob 2.0 was used as a core development tool throughout the project.

Bob was used to assist with:

* Project scaffolding
* Backend and frontend implementation
* API development
* React UI development
* Test generation
* Debugging integration issues
* Verification workflow improvements
* Security hardening
* Documentation and implementation tasks

The repository contains Bob task session evidence in:

```text
bob_sessions/
```

These screenshots document the Bob-assisted development work performed by the team.

---

## 📁 Project Structure

```text
devproof-ai/
│
├── frontend/                  # React + Vite frontend
│
├── backend/                   # FastAPI backend
│   ├── main.py
│   ├── requirements.txt
│   ├── .env.example
│   ├── db/
│   ├── llm/
│   ├── models/
│   ├── routers/
│   ├── services/
│   ├── sample_projects/
│   ├── tests/
│   ├── data/                  # gitignored
│   └── workspace/             # gitignored
│
├── bob_sessions/              # IBM Bob task session evidence
│
├── devproof-ai-plan.md        # Detailed MVP implementation plan
├── README.md
└── .gitignore
```

---

## ⚡ Quick Start

### Prerequisites

* Node.js 20+
* Python 3.11+

### 1. Clone

```bash
git clone https://github.com/srivigneshwaran/devproof-ai.git
cd devproof-ai
```

### 2. Start the Backend

```bash
cd backend

python -m venv .venv
```

#### Windows

```bash
.venv\Scripts\activate
```

#### macOS / Linux

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create the environment file:

```bash
cp .env.example .env
```

For local development without an AI API key:

```env
LLM_PROVIDER=mock
```

Start FastAPI:

```bash
python -m uvicorn main:app --reload --port 8000
```

Backend:

```text
http://localhost:8000
```

API documentation:

```text
http://localhost:8000/docs
```

---

### 3. Start the Frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

Frontend:

```text
http://localhost:5173
```

---

## 🔐 Security

The MVP includes several protections around uploaded source files and test execution.

### Upload restrictions

* Only `.py` files are accepted
* Maximum 5 files per upload
* Maximum 100 KB per file
* Path-traversal filenames are rejected
* Uploaded files are stored inside a session-specific workspace

### Test execution

* pytest is executed using a controlled subprocess
* `shell=False`
* Workspace directory is fixed and validated
* 30-second execution timeout
* Only `.py` files can be written into the workspace

### API

* Configurable CORS origins
* `X-Content-Type-Options: nosniff`
* Standardized error responses
* Internal filesystem paths and secrets are not returned in API errors

### MVP limitations

This is a hackathon MVP. It currently does not include:

* Authentication / authorization
* Rate limiting
* Docker/container sandboxing
* GitHub/GitLab OAuth
* Full repository ingestion
* CI/CD integration
* JavaScript/TypeScript test execution

---

## 📡 Core API

| Method | Endpoint                | Purpose                                 |
| ------ | ----------------------- | --------------------------------------- |
| `GET`  | `/api/projects`         | List sample projects                    |
| `POST` | `/api/projects/upload`  | Upload Python source files              |
| `POST` | `/api/analysis`         | Analyze project and identify root cause |
| `GET`  | `/api/analysis/{id}`    | Retrieve analysis                       |
| `POST` | `/api/fix`              | Generate fix suggestions                |
| `GET`  | `/api/fix/{id}`         | Retrieve fix suggestions                |
| `POST` | `/api/fix/{id}/approve` | Approve or reject fix                   |
| `POST` | `/api/verify`           | Generate tests and run verification     |
| `GET`  | `/api/report/{id}`      | Retrieve verification report            |

---

## 🧪 Verification Philosophy

DevProof AI is built around one principle:

> **A fix is not proven until its behavior has been tested.**

The system therefore separates:

**Suggestion**

```text
AI says:
"This code should be changed."
```

from:

**Verification**

```text
Tests run:
3 passed

Result:
Fix verified
```

This creates an auditable path from the original bug report to the final verification result.

---

## 📚 Documentation

For the detailed implementation plan, architecture, API contracts, workflow, subtasks, and design decisions, see:

[`devproof-ai-plan.md`](./devproof-ai-plan.md)

---

## 👥 Team

Built for the **IBM Bob 2.0 Hackathon — Bobathon 2.0**.

**DevProof AI**

> Don't just suggest a fix. Prove it works.
