"""
DevProof AI — Projects router (ST-3, ST-9).

Implements:
    GET  /api/projects              → Project[]
    GET  /api/projects/{id}/files   → ProjectFile[]
    POST /api/projects/upload       → UploadResult  (file upload for ad-hoc sessions)

All shapes match the REST API contract in devproof-ai-plan.md exactly.

ST-9 upload security:
  - Only .py files accepted (HTTP 400 on bad extension).
  - Maximum _MAX_FILES files per upload (HTTP 400 on excess).
  - Maximum _MAX_FILE_BYTES per file (HTTP 400 on oversize).
  - Filename path-traversal guard: only the basename is used; any filename
    containing path separators or that resolves outside the workspace is
    rejected with HTTP 400.
"""

import os
import uuid
from pathlib import Path
from typing import Annotated

import aiofiles
from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from services.project_service import get_project_files, list_projects

router = APIRouter(prefix="/api/projects", tags=["projects"])

# ---------------------------------------------------------------------------
# Upload constraints (ST-3 todo item 7)
# ---------------------------------------------------------------------------
_MAX_FILES = 5
_MAX_FILE_BYTES = 100 * 1024  # 100 KB per file
_WORKSPACE_BASE = Path(__file__).resolve().parent.parent / "workspace"


# ---------------------------------------------------------------------------
# Response models — minimal Pydantic shapes matching the API contract.
# Full models package is added in ST-4; these are scoped to ST-3 only.
# ---------------------------------------------------------------------------

class Project(BaseModel):
    id: str
    name: str
    description: str
    file_count: int


class ProjectFile(BaseModel):
    path: str
    description: str


class UploadResult(BaseModel):
    session_file_paths: list[str]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("", response_model=list[Project], summary="List all sample projects")
def list_projects_endpoint():
    """
    Return metadata for every controlled sample project.

    Projects are discovered from backend/sample_projects/ by reading each
    project.json manifest.  No project code is executed.
    """
    return list_projects()


@router.get(
    "/upload",  # must be declared BEFORE /{id}/files to avoid route shadowing
    include_in_schema=False,
)
def upload_placeholder():
    """Placeholder so that GET /api/projects/upload returns 405 not 404."""
    raise HTTPException(status_code=405, detail="Use POST /api/projects/upload")


@router.get("/{project_id}/files", response_model=list[ProjectFile], summary="List project files")
def get_files_endpoint(project_id: str):
    """
    Return the file manifest for the given sample project.
    """
    files = get_project_files(project_id)
    if files is None:
        raise HTTPException(status_code=404, detail=f"Project '{project_id}' not found")
    return files


def _safe_filename(filename: str) -> str:
    """
    Return the safe basename for an uploaded filename.

    Raises HTTPException 400 if the filename:
    - is empty
    - contains path separators (path-traversal attempt)
    - does not have a .py extension

    Only the basename is ever used — directory components are stripped
    defensively before the safety check.
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Filename must not be empty")

    # Reject filenames that contain explicit path separators before stripping.
    # Path.name strips them silently; we want to explicitly reject traversal
    # attempts rather than silently accepting only the basename.
    if "/" in filename or "\\" in filename:
        raise HTTPException(
            status_code=400,
            detail="Filename must not contain path separators",
        )

    safe = Path(filename).name  # strip any remaining . or similar artefacts

    if not safe:
        raise HTTPException(status_code=400, detail="Filename resolves to empty after sanitisation")

    if not safe.endswith(".py"):
        raise HTTPException(
            status_code=400,
            detail=f"Only .py files are accepted; '{safe}' is not allowed",
        )

    return safe


@router.post("/upload", response_model=UploadResult, summary="Upload .py files for a session")
async def upload_files_endpoint(files: Annotated[list[UploadFile], File(alias="files[]")]):
    """
    Accept up to 5 `.py` files (max 100 KB each) and save them to a new
    per-session workspace directory.

    ST-9 constraints enforced:
    - Only .py files accepted (HTTP 400 on bad extension or path traversal).
    - Maximum 5 files per upload (HTTP 400 on excess).
    - Maximum 100 KB per file (HTTP 400 on oversize).
    - Filename path-traversal guard: path separators in filename → HTTP 400.
    - Files are saved under workspace/{session_id}/ using the safe basename only.
    """
    if len(files) == 0:
        raise HTTPException(status_code=400, detail="At least one file is required")
    if len(files) > _MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Maximum {_MAX_FILES} files per upload")

    # Validate filenames, extensions, and sizes before writing anything.
    validated: list[tuple[str, bytes]] = []
    for upload in files:
        raw_filename = upload.filename or ""
        safe_name = _safe_filename(raw_filename)  # raises HTTP 400 on bad name

        content = await upload.read()
        if len(content) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=400,
                detail=f"File '{safe_name}' exceeds the 100 KB limit",
            )
        validated.append((safe_name, content))

    # Create a unique session workspace directory
    session_id = str(uuid.uuid4())
    session_dir = _WORKSPACE_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    for safe_name, content in validated:
        dest = session_dir / safe_name
        # Belt-and-suspenders: ensure dest resolves inside session_dir.
        if not str(dest.resolve()).startswith(str(session_dir.resolve())):
            raise HTTPException(
                status_code=400,
                detail=f"Path traversal detected for file '{safe_name}'",
            )
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        saved_paths.append(safe_name)

    return UploadResult(session_file_paths=saved_paths)
