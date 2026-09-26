"""
DevProof AI — Project Service (ST-3).

Discovers controlled sample projects from backend/sample_projects/ by reading
each sub-directory's project.json manifest.  No project code is executed.
"""

import json
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Pydantic-free data classes (models are added fully in ST-4).
# We keep things minimal here — plain dicts and typed dicts avoid a circular
# dependency before the models package exists.
# ---------------------------------------------------------------------------

_SAMPLE_PROJECTS_DIR = Path(__file__).resolve().parent.parent / "sample_projects"


def _load_manifest(project_dir: Path) -> Optional[dict]:
    """Read and parse a project.json from *project_dir*.  Returns None on error."""
    manifest_path = project_dir / "project.json"
    if not manifest_path.is_file():
        return None
    try:
        return json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def list_projects() -> list[dict]:
    """
    Return metadata for every valid sample project.

    Scans backend/sample_projects/ for sub-directories that contain a
    project.json manifest and returns a list of Project dicts shaped as:

        {
            "id":          str,
            "name":        str,
            "description": str,
            "file_count":  int,
        }

    No project source code is read or executed.
    """
    if not _SAMPLE_PROJECTS_DIR.is_dir():
        return []

    projects: list[dict] = []

    for project_dir in sorted(_SAMPLE_PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir():
            continue

        manifest = _load_manifest(project_dir)
        if manifest is None:
            continue

        files: list[dict] = manifest.get("files", [])
        projects.append(
            {
                "id": manifest.get("id", project_dir.name),
                "name": manifest.get("name", project_dir.name),
                "description": manifest.get("description", ""),
                "file_count": len(files),
            }
        )

    return projects


def get_project_files(project_id: str) -> Optional[list[dict]]:
    """
    Return the file list for the given project id.

    Each entry is shaped as:
        { "path": str, "description": str }

    Returns None when the project is not found.
    """
    project_dir = _SAMPLE_PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        return None

    manifest = _load_manifest(project_dir)
    if manifest is None:
        return None

    return [
        {"path": f.get("path", ""), "description": f.get("description", "")}
        for f in manifest.get("files", [])
    ]
