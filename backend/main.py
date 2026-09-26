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
ST-6: Fix router registered.
      POST /api/fix, GET /api/fix/{session_id},
      POST /api/fix/{session_id}/approve
ST-7: Verify and Report routers registered.
      POST /api/verify
      GET  /api/report/{session_id}
ST-8: Global exception handler (unhandled → 500), HTTPException handler
      (normalized error envelope), and startup env-var validation.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db.database import init_db
from llm.factory import get_provider, validate_env
from routers.analysis import router as analysis_router
from routers.fix import router as fix_router
from routers.projects import router as projects_router
from routers.report import router as report_router
from routers.sessions import router as sessions_router
from routers.verify import router as verify_router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # ST-8: Validate required environment variables before anything else.
    # Raises RuntimeError with a clear message if mandatory vars are missing.
    validate_env()

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
# ST-8: Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """
    Normalize all HTTPException responses to the standard envelope:

        { "error": "<short label>", "detail": "<message>" }

    This applies to every route (404, 409, 422, 503, …).
    """
    status_labels: dict[int, str] = {
        400: "Bad Request",
        401: "Unauthorized",
        403: "Forbidden",
        404: "Not Found",
        409: "Conflict",
        422: "Unprocessable Entity",
        500: "Internal Server Error",
        503: "Service Unavailable",
    }
    label = status_labels.get(exc.status_code, f"HTTP {exc.status_code}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": label, "detail": exc.detail},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Normalize Pydantic RequestValidationError (422) to the standard envelope.

    FastAPI raises this for malformed/missing request body fields.
    """
    return JSONResponse(
        status_code=422,
        content={"error": "Unprocessable Entity", "detail": exc.errors()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all handler for any unhandled exception.

    Returns HTTP 500 with the standard error envelope so that no internal
    tracebacks are exposed to callers.
    """
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "detail": "An unexpected error occurred. Please try again later.",
        },
    )


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(projects_router)   # ST-3
app.include_router(sessions_router)   # ST-5
app.include_router(analysis_router)   # ST-5
app.include_router(fix_router)        # ST-6
app.include_router(verify_router)     # ST-7
app.include_router(report_router)     # ST-7


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
