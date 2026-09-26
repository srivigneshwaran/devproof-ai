"""
DevProof AI — Analysis Service (ST-5, ST-8).

Implements the AI step that reads the bug description + file contents and
returns ranked relevant files with root causes.

    analyze(session_id, bug_description, file_contents, llm) -> dict

Returns a dict matching the AnalysisResult JSON contract.

All LLM calls go through the LLMProvider.complete() abstraction — no direct
SDK usage.

ST-8: LLM call wrapped to raise LLMServiceError on any provider failure.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from llm.base import LLMProvider
from llm.exceptions import LLMServiceError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context limits
# ---------------------------------------------------------------------------
# Truncate each file's content to this many characters before sending to LLM
# to stay within context window limits.
_MAX_FILE_CHARS = 4000
# Maximum total character budget for all file contents combined.
_MAX_TOTAL_CHARS = 16000

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SAMPLE_PROJECTS_DIR = _BACKEND_DIR / "sample_projects"
_WORKSPACE_DIR = _BACKEND_DIR / "workspace"


# ---------------------------------------------------------------------------
# File content loading helpers
# ---------------------------------------------------------------------------


def _load_sample_project_files(project_id: str) -> dict[str, str]:
    """
    Read all .py file contents for a sample project.

    Returns a mapping of {relative_path: file_content}.
    Raises ValueError if the project is not found.
    """
    project_dir = _SAMPLE_PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise ValueError(f"Sample project '{project_id}' not found")

    manifest_path = project_dir / "project.json"
    if not manifest_path.is_file():
        raise ValueError(f"No manifest for project '{project_id}'")

    import json as _json
    manifest = _json.loads(manifest_path.read_text(encoding="utf-8"))
    files_meta = manifest.get("files", [])

    contents: dict[str, str] = {}
    for f in files_meta:
        rel_path = f.get("path", "")
        abs_path = project_dir / rel_path
        if abs_path.is_file():
            try:
                contents[rel_path] = abs_path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not read %s: %s", abs_path, exc)

    return contents


def _load_workspace_files(session_id: str) -> dict[str, str]:
    """
    Read all .py files from the most-recently-modified workspace directory.

    For 'upload' sessions the frontend uploads files via POST /api/projects/upload
    BEFORE creating the session. The upload creates workspace/<upload_uuid>/.
    Since the session_id is generated after the upload, we locate the most
    recently modified workspace directory that does not match the session_id
    (it will not yet exist when analysis is first run) or, if one matching the
    session_id exists, use that (future-proof for direct workspace seeding).

    Returns a mapping of {filename: file_content}.
    Returns an empty dict if no workspace files are found.
    """
    # First preference: workspace dir named after the session_id
    session_workspace = _WORKSPACE_DIR / session_id
    if session_workspace.is_dir():
        return _read_py_files(session_workspace)

    # Second preference: most recently modified workspace directory
    if not _WORKSPACE_DIR.is_dir():
        return {}

    workspace_dirs = sorted(
        (d for d in _WORKSPACE_DIR.iterdir() if d.is_dir()),
        key=lambda d: d.stat().st_mtime,
        reverse=True,
    )
    if workspace_dirs:
        chosen = workspace_dirs[0]
        logger.info(
            "Upload session %s: using workspace directory %s", session_id, chosen.name
        )
        return _read_py_files(chosen)

    return {}


def _read_py_files(directory: Path) -> dict[str, str]:
    """Read all .py files from *directory*. Returns {filename: content}."""
    contents: dict[str, str] = {}
    for py_file in sorted(directory.glob("*.py")):
        try:
            contents[py_file.name] = py_file.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Could not read %s: %s", py_file, exc)
    return contents


def _truncate_files(file_contents: dict[str, str]) -> dict[str, str]:
    """
    Truncate file contents to respect context limits.

    Each file is capped at _MAX_FILE_CHARS characters. The combined total is
    then capped at _MAX_TOTAL_CHARS (files are included in sorted order so
    truncation is deterministic).
    """
    truncated: dict[str, str] = {}
    total = 0
    for path, content in sorted(file_contents.items()):
        snippet = content[:_MAX_FILE_CHARS]
        if total + len(snippet) > _MAX_TOTAL_CHARS:
            remaining = _MAX_TOTAL_CHARS - total
            if remaining <= 0:
                break
            snippet = snippet[:remaining]
        truncated[path] = snippet
        total += len(snippet)
    return truncated


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_messages(bug_description: str, file_contents: dict[str, str]) -> list[dict]:
    """Build the chat messages list for the LLM analysis call."""
    system_prompt = (
        "You are an expert code reviewer and debugger. "
        "You will be given a bug description and the contents of one or more Python source files. "
        "Your task is to analyse the code and identify:\n"
        "1. Which files are most relevant to the reported bug (ranked by confidence).\n"
        "2. The probable root causes of the bug.\n\n"
        "Respond ONLY with a valid JSON object matching this exact schema — no markdown, "
        "no commentary, no code fences:\n"
        '{\n'
        '  "relevant_files": [\n'
        '    { "path": "<filename>", "confidence": <float 0-1>, "reason": "<one sentence>" }\n'
        '  ],\n'
        '  "root_causes": [\n'
        '    { "description": "<root cause>", "file": "<filename>", "line_hint": <int or null> }\n'
        '  ]\n'
        '}'
    )

    file_sections: list[str] = []
    for path, content in sorted(file_contents.items()):
        file_sections.append(f"=== {path} ===\n{content}")

    user_content = (
        f"Bug description:\n{bug_description}\n\n"
        "Source files:\n\n"
        + "\n\n".join(file_sections)
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------


def analyze(
    session_id: str,
    bug_description: str,
    project_id: str,
    llm: LLMProvider,
) -> dict:
    """
    Run analysis for the given session.

    Steps:
    1. Load file contents (sample project or uploaded workspace).
    2. Truncate to context limits.
    3. Build LLM messages and call llm.complete(json_mode=True).
    4. Parse and validate the JSON response.
    5. Return a dict matching the AnalysisResult contract.

    Raises:
        ValueError: If the project is not found or LLM response is invalid JSON.
        RuntimeError: Wraps any unexpected LLM error.
    """
    # 1. Load file contents
    if project_id == "upload":
        file_contents = _load_workspace_files(session_id)
        if not file_contents:
            logger.warning("No uploaded files found for session %s", session_id)
            # Return a minimal result rather than crashing the analysis
            return {
                "session_id": session_id,
                "relevant_files": [],
                "root_causes": [
                    {
                        "description": "No source files found for analysis.",
                        "file": "",
                        "line_hint": None,
                    }
                ],
            }
    else:
        file_contents = _load_sample_project_files(project_id)

    # 2. Truncate
    file_contents = _truncate_files(file_contents)

    # 3. Build messages and call LLM
    messages = _build_messages(bug_description, file_contents)

    try:
        raw_response = llm.complete(messages, json_mode=True)
    except Exception as exc:
        logger.error("LLM call failed for session %s: %s", session_id, exc)
        raise LLMServiceError(f"LLM analysis failed", exc) from exc

    # 4. Parse and validate
    try:
        payload = json.loads(raw_response)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.error(
            "LLM returned invalid JSON for session %s: %s", session_id, raw_response[:200]
        )
        raise LLMServiceError(f"LLM returned invalid JSON: {exc}", exc) from exc

    relevant_files = payload.get("relevant_files", [])
    root_causes = payload.get("root_causes", [])

    # Normalise: ensure required fields are present with sensible defaults
    normalised_files = []
    for rf in relevant_files:
        if isinstance(rf, dict) and "path" in rf:
            normalised_files.append(
                {
                    "path": str(rf.get("path", "")),
                    "confidence": float(rf.get("confidence", 0.5)),
                    "reason": str(rf.get("reason", "")),
                }
            )

    normalised_causes = []
    for rc in root_causes:
        if isinstance(rc, dict) and "description" in rc:
            normalised_causes.append(
                {
                    "description": str(rc.get("description", "")),
                    "file": str(rc.get("file", "")),
                    "line_hint": rc.get("line_hint"),  # may be None
                }
            )

    return {
        "session_id": session_id,
        "relevant_files": normalised_files,
        "root_causes": normalised_causes,
    }
