"""
DevProof AI — Fix router (ST-6).

Implements:
    POST /api/fix                             → FixList
    GET  /api/fix/{session_id}                → FixList
    POST /api/fix/{session_id}/approve        → { "status": "fix_approved" | "fix_rejected" }

All shapes match the REST API contract in devproof-ai-plan.md exactly.
"""

import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.database import get_connection
from llm.exceptions import LLMServiceError
from models.fix import FixApproval, FixList, FixSuggestion
from services.fix_service import generate_fixes

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/fix", tags=["fix"])


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class FixRequest(BaseModel):
    """Request body for POST /api/fix."""

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


def _get_fix_rows(session_id: str, conn):
    """Return all fix suggestion rows for a session, ordered by creation time."""
    return conn.execute(
        "SELECT * FROM fix_suggestions WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()


def _row_to_fix_suggestion(row) -> FixSuggestion:
    """Convert a sqlite3.Row from fix_suggestions to a FixSuggestion model."""
    return FixSuggestion(
        id=row["id"],
        file_path=row["file_path"],
        original=row["original"],
        suggested=row["suggested"],
        explanation=row["explanation"],
    )


def _rows_to_fix_list(session_id: str, rows) -> FixList:
    """Convert a list of fix_suggestions rows into a FixList."""
    fixes = [_row_to_fix_suggestion(r) for r in rows]
    return FixList(session_id=session_id, fixes=fixes)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=FixList,
    status_code=200,
    summary="Generate fix suggestions for a session",
)
def generate_fix(body: FixRequest, request: Request) -> FixList:
    """
    Trigger AI fix suggestion generation for the given session.

    - Session must exist (404 otherwise).
    - An analysis must exist for the session (404 otherwise).
    - Calls the LLM to produce an original→suggested code change per relevant file.
    - Persists all fix suggestions to the ``fix_suggestions`` table.
    - Updates ``sessions.status`` to ``'fix_proposed'``.

    Returns a ``FixList`` matching the REST API contract.

    Raises:
    - 404 if the session does not exist.
    - 404 if no analysis has been run for this session.
    - 503 if the LLM call fails.
    """
    session_id = body.session_id.strip()

    with get_connection() as conn:
        session_row = _get_session(session_id, conn)
        project_id: str = session_row["project_id"]
        bug_description: str = session_row["bug_description"]

        analysis_row = _get_analysis_row(session_id, conn)

    if analysis_row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No analysis found for session '{session_id}'. "
                "Run POST /api/analysis first."
            ),
        )

    # Reconstruct the analysis result dict for the service.
    analysis_result = {
        "session_id": session_id,
        "relevant_files": json.loads(analysis_row["relevant_files"]),
        "root_causes": json.loads(analysis_row["root_causes"]),
    }

    # Generate fixes via service (uses LLMProvider abstraction).
    llm = request.app.state.llm
    try:
        fix_dicts = generate_fixes(
            session_id=session_id,
            bug_description=bug_description,
            project_id=project_id,
            analysis_result=analysis_result,
            llm=llm,
        )
    except LLMServiceError as exc:
        logger.error("Fix generation LLM failure for session %s: %s", session_id, exc)
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        logger.error("Fix generation ValueError for session %s: %s", session_id, exc)
        raise HTTPException(status_code=422, detail=str(exc))

    # Persist fixes and update session status.
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_connection() as conn:
        for fix in fix_dicts:
            conn.execute(
                """
                INSERT INTO fix_suggestions
                    (id, session_id, file_path, original, suggested, explanation, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    fix["id"],
                    session_id,
                    fix["file_path"],
                    fix["original"],
                    fix["suggested"],
                    fix["explanation"],
                    now,
                ),
            )
        conn.execute(
            "UPDATE sessions SET status = 'fix_proposed' WHERE id = ?",
            (session_id,),
        )

    fixes = [
        FixSuggestion(
            id=f["id"],
            file_path=f["file_path"],
            original=f["original"],
            suggested=f["suggested"],
            explanation=f["explanation"],
        )
        for f in fix_dicts
    ]
    return FixList(session_id=session_id, fixes=fixes)


@router.get(
    "/{session_id}",
    response_model=FixList,
    summary="Get fix suggestions for a session",
)
def get_fixes(session_id: str) -> FixList:
    """
    Retrieve all previously generated fix suggestions for the given session.

    - 404 if the session does not exist.
    - 404 if no fixes have been generated for this session yet.
    """
    with get_connection() as conn:
        _get_session(session_id, conn)
        rows = _get_fix_rows(session_id, conn)

    if not rows:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No fix suggestions found for session '{session_id}'. "
                "Run POST /api/fix first."
            ),
        )

    return _rows_to_fix_list(session_id, rows)


@router.post(
    "/{session_id}/approve",
    status_code=200,
    summary="Approve or reject fix suggestions for a session",
)
def approve_fix(session_id: str, body: FixApproval, request: Request) -> dict:
    """
    Record the human approval or rejection of the fix suggestions.

    - Session must exist (404 otherwise).
    - Fix suggestions must exist (404 otherwise).
    - Returns HTTP 409 if the session has already been approved or rejected.
    - Writes to ``fix_approvals`` table.
    - Updates ``sessions.status`` to ``'fix_approved'`` or ``'fix_rejected'``.

    Returns: ``{ "status": "fix_approved" }`` or ``{ "status": "fix_rejected" }``
    """
    with get_connection() as conn:
        session_row = _get_session(session_id, conn)
        current_status: str = session_row["status"]

        # Enforce: cannot re-approve/re-reject an already-decided session.
        if current_status in ("fix_approved", "fix_rejected"):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Session '{session_id}' has already been "
                    f"{'approved' if current_status == 'fix_approved' else 'rejected'}. "
                    "Cannot approve or reject again."
                ),
            )

        # Fix suggestions must exist before approval is meaningful.
        fix_rows = _get_fix_rows(session_id, conn)

    if not fix_rows:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No fix suggestions found for session '{session_id}'. "
                "Run POST /api/fix first."
            ),
        )

    approval_id = str(uuid.uuid4())
    new_status = "fix_approved" if body.approved else "fix_rejected"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fix_approvals (id, session_id, approved, feedback, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                session_id,
                1 if body.approved else 0,
                body.feedback,
                now,
            ),
        )
        conn.execute(
            "UPDATE sessions SET status = ? WHERE id = ?",
            (new_status, session_id),
        )

    return {"status": new_status}
