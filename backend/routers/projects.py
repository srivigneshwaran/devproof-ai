"""
DevProof AI — Projects router (ST-3).

Implements:
    GET  /api/projects              → Project[]
    GET  /api/projects/{id}/files   → ProjectFile[]
    POST /api/projects/upload       → UploadResult  (file upload for ad-hoc sessions)

All shapes match the REST API contract in devproof-ai-plan.md exactly.
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


@router.post("/upload", response_model=UploadResult, summary="Upload .py files for a session")
async def upload_files_endpoint(files: Annotated[list[UploadFile], File(alias="files[]")]):
    """
    Accept up to 5 `.py` files (max 100 KB each) and save them to a new
    per-session workspace directory.

    Constraints enforced:
    - Only .py files are accepted (HTTP 422 otherwise).
    - Maximum 5 files per upload.
    - Maximum 100 KB per file.
    """
    if len(files) == 0:
        raise HTTPException(status_code=422, detail="At least one file is required")
    if len(files) > _MAX_FILES:
        raise HTTPException(status_code=422, detail=f"Maximum {_MAX_FILES} files per upload")

    # Validate extensions and sizes before writing anything
    for upload in files:
        filename = upload.filename or ""
        if not filename.endswith(".py"):
            raise HTTPException(
                status_code=422,
                detail=f"Only .py files are accepted; '{filename}' is not allowed",
            )
        content = await upload.read()
        if len(content) > _MAX_FILE_BYTES:
            raise HTTPException(
                status_code=422,
                detail=f"File '{filename}' exceeds the 100 KB limit",
            )
        await upload.seek(0)  # reset for writing

    # Create a unique session workspace directory
    session_id = str(uuid.uuid4())
    session_dir = _WORKSPACE_BASE / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    saved_paths: list[str] = []
    for upload in files:
        filename = upload.filename or f"file_{len(saved_paths)}.py"
        dest = session_dir / Path(filename).name
        content = await upload.read()
        async with aiofiles.open(dest, "wb") as f:
            await f.write(content)
        saved_paths.append(filename)

    return UploadResult(session_file_paths=saved_paths)
