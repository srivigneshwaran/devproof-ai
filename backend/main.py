"""
DevProof AI — FastAPI application entry point.

ST-1: Scaffold, CORS, lifespan, and health endpoint.
ST-2: LLM provider instantiated once at startup and stored on app.state.llm.
ST-3: Projects router registered (GET /api/projects, GET /api/projects/{id}/files,
      POST /api/projects/upload).
ST-4: Full SQLite schema applied via init_db() on startup; Pydantic models
      available in backend/models/.
ST-5: Sessions and Analysis routers registered.
      POST /api/sessions, GET /api/sessions, GET /api/sessions/{id}
      POST /api/analysis, GET /api/analysis/{session_id}
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db
from llm.factory import get_provider
from routers.analysis import router as analysis_router
from routers.projects import router as projects_router
from routers.sessions import router as sessions_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    init_db()

    # ST-2: initialise the LLM provider once and attach it to app state so
    # every request handler can access it via `request.app.state.llm`.
    app.state.llm = get_provider()
    logger.info("LLM provider ready: %s", type(app.state.llm).__name__)

    yield
    # Shutdown (nothing to clean up yet)


app = FastAPI(
    title="DevProof AI",
    description="AI-powered developer workflow assistant — proves fixes work.",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the Vite dev server (default port 5173) and any configured
# frontend origin. In production, restrict to the deployed frontend URL.
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(projects_router)   # ST-3
app.include_router(sessions_router)   # ST-5
app.include_router(analysis_router)   # ST-5


# ---------------------------------------------------------------------------
# Health endpoint (ST-1)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
def health_check():
    """
    Returns 200 OK when the server is running.
    Used by the frontend to confirm backend availability.
    """
    return {"status": "ok", "service": "devproof-ai"}
