"""
DevProof AI — Analysis router (ST-5).

Implements:
    POST /api/analysis                  → AnalysisResult
    GET  /api/analysis/{session_id}     → AnalysisResult

All shapes match the REST API contract in devproof-ai-plan.md exactly.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.database import get_connection
from models.analysis import AnalysisResult
from services.analysis_service import analyze

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class AnalysisRequest(BaseModel):
    """Request body for POST /api/analysis."""

    session_id: str


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _get_session(session_id: str, conn):
    """Fetch a session row or raise 404."""
    row = conn.execute(
        "SELECT * FROM sessions WHERE id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return row


def _get_analysis_row(session_id: str, conn):
    """Return the most recent analysis row for a session, or None."""
    return conn.execute(
        "SELECT * FROM analyses WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()


def _row_to_analysis_result(row) -> AnalysisResult:
    """Convert a sqlite3.Row from the analyses table into an AnalysisResult."""
    relevant_files = json.loads(row["relevant_files"])
    root_causes = json.loads(row["root_causes"])
    return AnalysisResult(
        session_id=row["session_id"],
        relevant_files=relevant_files,
        root_causes=root_causes,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=AnalysisResult,
    status_code=200,
    summary="Run analysis for a session",
)
def run_analysis(body: AnalysisRequest, request: Request) -> AnalysisResult:
    """
    Trigger AI analysis for the given session.

    - Reads file contents from the sample project workspace or the uploaded
      file workspace.
    - Calls the LLM to identify relevant files and root causes.
    - Persists the result to the ``analyses`` table.
    - Updates ``sessions.status`` to ``'analyzed'``.

    Returns the ``AnalysisResult`` matching the REST API contract.

    Raises:
    - 404 if the session does not exist.
    - 503 if the LLM call fails.
    """
    session_id = body.session_id.strip()

    with get_connection() as conn:
        session_row = _get_session(session_id, conn)
        project_id: str = session_row["project_id"]
        bug_description: str = session_row["bug_description"]

    # Run analysis via the service
    llm = request.app.state.llm
    try:
        result_dict = analyze(
            session_id=session_id,
            bug_description=bug_description,
            project_id=project_id,
            llm=llm,
        )
    except ValueError as exc:
        logger.error("Analysis ValueError for session %s: %s", session_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))
    except RuntimeError as exc:
        logger.error("Analysis LLM failure for session %s: %s", session_id, exc)
        raise HTTPException(status_code=503, detail=str(exc))

    # Persist result
    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO analyses (id, session_id, relevant_files, root_causes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                session_id,
                json.dumps(result_dict["relevant_files"]),
                json.dumps(result_dict["root_causes"]),
                now,
            ),
        )
        conn.execute(
            "UPDATE sessions SET status = 'analyzed' WHERE id = ?",
            (session_id,),
        )

    return AnalysisResult(**result_dict)


@router.get(
    "/{session_id}",
    response_model=AnalysisResult,
    summary="Get analysis result for a session",
)
def get_analysis(session_id: str) -> AnalysisResult:
    """
    Retrieve a previously computed analysis for the given session_id.

    - 404 if the session does not exist.
    - 404 if no analysis has been run for this session yet.
    """
    with get_connection() as conn:
        # Confirm session exists
        _get_session(session_id, conn)

        # Fetch analysis
        row = _get_analysis_row(session_id, conn)

    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for session '{session_id}'. "
                   "Run POST /api/analysis first.",
        )

    return _row_to_analysis_result(row)
