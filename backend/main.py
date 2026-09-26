"""
DevProof AI — FastAPI application entry point.

ST-1: Scaffold, CORS, lifespan, and health endpoint.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    init_db()
    yield
    # Shutdown (nothing to clean up in ST-1)


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
# Health endpoint (ST-1)
# ---------------------------------------------------------------------------

@app.get("/health", tags=["health"])
def health_check():
    """
    Returns 200 OK when the server is running.
    Used by the frontend to confirm backend availability.
    """
    return {"status": "ok", "service": "devproof-ai"}
