"""
DevProof AI — Report router (ST-7).

Implements:
    GET /api/report/{session_id}    → VerificationReport

Retrieves a previously generated verification report for the given session.

All shapes match the REST API contract in devproof-ai-plan.md exactly.
"""

import json
import logging

from fastapi import APIRouter, HTTPException

from db.database import get_connection
from models.analysis import FileRelevance, RootCause
from models.fix import FixSuggestion
from models.report import GeneratedTest, VerificationReport

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/report", tags=["report"])


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


def _get_report_row(session_id: str, conn):
    """Return the most recent report row for a session, or None."""
    return conn.execute(
        "SELECT * FROM reports WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()


def _get_analysis_row(session_id: str, conn):
    """Return the most recent analysis row for a session, or None."""
    return conn.execute(
        "SELECT * FROM analyses WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
        (session_id,),
    ).fetchone()


def _get_fix_rows(session_id: str, conn):
    """Return all fix suggestion rows for a session."""
    return conn.execute(
        "SELECT * FROM fix_suggestions WHERE session_id = ? ORDER BY created_at ASC",
        (session_id,),
    ).fetchall()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/{session_id}",
    response_model=VerificationReport,
    summary="Get verification report for a session",
)
def get_report(session_id: str) -> VerificationReport:
    """
    Retrieve the verification report for the given session_id.

    - 404 if the session does not exist.
    - 404 if no verification report has been generated for this session yet.
    """
    with get_connection() as conn:
        session_row = _get_session(session_id, conn)
        report_row = _get_report_row(session_id, conn)
        analysis_row = _get_analysis_row(session_id, conn)
        fix_rows = _get_fix_rows(session_id, conn)

    if report_row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No verification report found for session '{session_id}'. "
                "Run POST /api/verify first."
            ),
        )

    # Rebuild relevant_files and root_causes from the analysis.
    relevant_files: list[FileRelevance] = []
    root_causes: list[RootCause] = []
    if analysis_row is not None:
        for rf in json.loads(analysis_row["relevant_files"]):
            if isinstance(rf, dict):
                relevant_files.append(FileRelevance(**rf))
        for rc in json.loads(analysis_row["root_causes"]):
            if isinstance(rc, dict):
                root_causes.append(RootCause(**rc))

    # Rebuild fixes.
    fixes = [
        FixSuggestion(
            id=row["id"],
            file_path=row["file_path"],
            original=row["original"],
            suggested=row["suggested"],
            explanation=row["explanation"],
        )
        for row in fix_rows
    ]

    # Rebuild generated tests.
    tests_generated: list[GeneratedTest] = []
    for t in json.loads(report_row["tests_generated"]):
        if isinstance(t, dict):
            tests_generated.append(
                GeneratedTest(file=t.get("file", ""), code=t.get("code", ""))
            )

    return VerificationReport(
        session_id=session_id,
        project_name=session_row["project_name"],
        bug_description=session_row["bug_description"],
        verdict=report_row["verdict"],
        relevant_files=relevant_files,
        root_causes=root_causes,
        fixes=fixes,
        tests_generated=tests_generated,
        test_output=report_row["test_output"],
        tests_passed=report_row["tests_passed"],
        tests_failed=report_row["tests_failed"],
        summary=report_row["summary"],
        created_at=report_row["created_at"],
    )
