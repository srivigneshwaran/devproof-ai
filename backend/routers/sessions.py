"""
DevProof AI — Sessions router (ST-5).

Implements:
    POST /api/sessions       → Session   (create a new session)
    GET  /api/sessions       → Session[] (list all sessions)
    GET  /api/sessions/{id}  → Session   (get a single session)

All shapes match the REST API contract in devproof-ai-plan.md exactly.
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from db.database import get_connection
from models.session import Session, SessionCreate, SessionStatus
from services.project_service import list_projects

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _row_to_session(row) -> Session:
    """Convert a sqlite3.Row to a Session Pydantic model."""
    return Session(
        id=row["id"],
        project_id=row["project_id"],
        project_name=row["project_name"],
        bug_description=row["bug_description"],
        status=SessionStatus(row["status"]),
        created_at=row["created_at"],
    )


def _resolve_project_name(project_id: str) -> str:
    """
    Return the human-readable project name for the given project_id.

    For sample projects this reads the manifest. For uploaded-file sessions
    (project_id == 'upload') we return a sentinel that is overwritten later.
    """
    if project_id == "upload":
        return "Uploaded Files"
    projects = list_projects()
    for p in projects:
        if p["id"] == project_id:
            return p["name"]
    return project_id  # fallback: use the id as the name


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", response_model=Session, status_code=201, summary="Create a new session")
def create_session(body: SessionCreate) -> Session:
    """
    Create a new analysis session.

    For sample projects, validates the project_id exists.
    For uploaded-file sessions, project_id must be ``"upload"``.
    """
    project_id = body.project_id.strip()

    # Validate: must be a known sample project or the 'upload' sentinel.
    if project_id != "upload":
        known_ids = {p["id"] for p in list_projects()}
        if project_id not in known_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Project '{project_id}' not found. "
                       "Use a valid sample project id or 'upload' for uploaded files.",
            )

    project_name = _resolve_project_name(project_id)
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, created_at, project_id, project_name, bug_description, status)
            VALUES (?, ?, ?, ?, ?, 'created')
            """,
            (session_id, now, project_id, project_name, body.bug_description),
        )

    return Session(
        id=session_id,
        project_id=project_id,
        project_name=project_name,
        bug_description=body.bug_description,
        status=SessionStatus.created,
        created_at=now,
    )


@router.get("", response_model=list[Session], summary="List all sessions")
def list_sessions() -> list[Session]:
    """Return all sessions ordered by creation time (newest first)."""
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()
    return [_row_to_session(r) for r in rows]


@router.get("/{session_id}", response_model=Session, summary="Get a session by ID")
def get_session(session_id: str) -> Session:
    """Return the session with the given id, or 404 if not found."""
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")
    return _row_to_session(row)
