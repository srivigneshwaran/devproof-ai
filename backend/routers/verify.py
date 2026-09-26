"""
DevProof AI — Verify router (ST-7).

Implements:
    POST /api/verify    → VerificationReport

Single orchestrated endpoint:
  1. Validate session (must be fix_approved — HTTP 409 otherwise)
  2. Load approved fixes and analysis from DB
  3. LLM generates pytest test code (test_service)
  4. Apply fix + run controlled pytest in workspace (validation_service)
  5. LLM generates summary + compute verdict (report_service)
  6. Persist VerificationReport; update session status to 'verified'
  7. Return VerificationReport

All shapes match the REST API contract in devproof-ai-plan.md exactly.
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from db.database import get_connection
from models.report import VerificationReport
from services.report_service import compile_report
from services.test_service import generate_tests
from services.validation_service import run_tests

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/verify", tags=["verify"])


# ---------------------------------------------------------------------------
# Request body
# ---------------------------------------------------------------------------


class VerifyRequest(BaseModel):
    """Request body for POST /api/verify."""

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
        raise HTTPException(
            status_code=404,
            detail=f"Session '{session_id}' not found.",
        )
    return row


def _get_analysis(session_id: str, conn):
    """Fetch the most recent analysis row for a session, or None."""
    return conn.execute(
        "SELECT * FROM analyses WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()


def _get_fixes(session_id: str, conn):
    """Fetch all fix_suggestions rows for a session."""
    return conn.execute(
        "SELECT * FROM fix_suggestions WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=VerificationReport,
    status_code=200,
    summary="Run full verification for an approved fix",
)
def run_verification(body: VerifyRequest, request: Request) -> VerificationReport:
    """
    Orchestrate the full verification workflow.

    **Requires** the session to be in ``fix_approved`` status.
    Returns HTTP 409 if the fix has not been explicitly approved.

    Workflow:
    1. Load session — 404 if not found
    2. Guard: session.status must be 'fix_approved' — 409 otherwise
    3. Load analysis and fix suggestions from DB
    4. LLM generates pytest tests for each fix
    5. Apply fix to workspace; run controlled pytest with 30s timeout
    6. LLM generates a 2-3 sentence summary; verdict computed from counts
    7. Persist VerificationReport; update session status to 'verified'
    8. Return VerificationReport

    Raises:
    - 404 if the session does not exist
    - 409 if the fix has not been approved (status != 'fix_approved')
    - 503 if the LLM test generation fails
    """
    session_id = body.session_id.strip()

    with get_connection() as conn:
        session_row = _get_session(session_id, conn)
        current_status: str = session_row["status"]
        project_id: str = session_row["project_id"]
        project_name: str = session_row["project_name"]
        bug_description: str = session_row["bug_description"]

        # ---------------------------------------------------------------
        # Human approval gate — the core safety invariant.
        # Only 'fix_approved' sessions may be verified.
        # ---------------------------------------------------------------
        if current_status != "fix_approved":
            status_messages = {
                "created":      "Analysis has not been run yet.",
                "analyzed":     "Fix suggestions have not been generated yet.",
                "fix_proposed": "The fix has not been approved yet. "
                                "Call POST /api/fix/{session_id}/approve first.",
                "fix_rejected": "The fix was rejected. It cannot be verified.",
                "verified":     "This session has already been verified.",
            }
            detail = status_messages.get(
                current_status,
                f"Session status is '{current_status}' — fix must be approved first.",
            )
            raise HTTPException(
                status_code=409,
                detail=detail,
            )

        # Load analysis
        analysis_row = _get_analysis(session_id, conn)
        fix_rows = _get_fixes(session_id, conn)

    # Build plain dicts for service layer (avoids sqlite3.Row pickling issues).
    analysis_result: dict = {
        "relevant_files": [],
        "root_causes": [],
    }
    if analysis_row is not None:
        analysis_result = {
            "relevant_files": json.loads(analysis_row["relevant_files"]),
            "root_causes": json.loads(analysis_row["root_causes"]),
        }

    fixes: list[dict] = [
        {
            "id": row["id"],
            "session_id": session_id,
            "file_path": row["file_path"],
            "original": row["original"],
            "suggested": row["suggested"],
            "explanation": row["explanation"],
        }
        for row in fix_rows
    ]

    llm = request.app.state.llm

    # ------------------------------------------------------------------
    # Step 1: Generate tests via LLM
    # ------------------------------------------------------------------
    try:
        generated_tests = generate_tests(
            session_id=session_id,
            fixes=fixes,
            bug_description=bug_description,
            llm=llm,
        )
    except RuntimeError as exc:
        logger.error("Test generation failed for session %s: %s", session_id, exc)
        raise HTTPException(
            status_code=503,
            detail=f"LLM test generation failed: {exc}",
        )

    # ------------------------------------------------------------------
    # Step 2: Run tests in controlled workspace
    # ------------------------------------------------------------------
    validation_result = run_tests(
        session_id=session_id,
        generated_tests=generated_tests,
        fixes=fixes,
        project_id=project_id,
    )

    # ------------------------------------------------------------------
    # Step 3: Compile report (LLM summary + persist)
    # ------------------------------------------------------------------
    report = compile_report(
        session_id=session_id,
        validation_result=validation_result,
        generated_tests=generated_tests,
        fixes=fixes,
        analysis_result=analysis_result,
        project_name=project_name,
        bug_description=bug_description,
        llm=llm,
    )

    return report
