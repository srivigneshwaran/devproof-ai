"""
DevProof AI — Fix Suggestion Service (ST-6, ST-8).

Implements fix suggestion generation.

    generate_fixes(session_id, analysis_result, file_contents, llm) -> list[dict]

For each relevant file with confidence > 0.6, a concrete original→suggested
code change is produced using the LLMProvider abstraction.

All LLM calls go through the LLMProvider.complete() abstraction — no direct
SDK usage.

ST-8: LLM calls wrapped to raise LLMServiceError on any provider failure.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from llm.base import LLMProvider
from llm.exceptions import LLMServiceError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Context limits — each file is capped before being sent to the LLM.
# ---------------------------------------------------------------------------
_MAX_FILE_CHARS = 4000
# Only generate fixes for files above this confidence threshold.
_CONFIDENCE_THRESHOLD = 0.6

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_SAMPLE_PROJECTS_DIR = _BACKEND_DIR / "sample_projects"
_WORKSPACE_DIR = _BACKEND_DIR / "workspace"


# ---------------------------------------------------------------------------
# File content loading (mirrors analysis_service helpers)
# ---------------------------------------------------------------------------


def _load_file_content(file_path: str, project_id: str, session_id: str) -> Optional[str]:
    """
    Attempt to load the content of *file_path* from either the sample project
    directory or the session workspace.

    Returns the file content as a string, or None if not found.
    """
    # Try sample project first
    if project_id != "upload":
        candidate = _SAMPLE_PROJECTS_DIR / project_id / file_path
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                pass

    # Try session workspace
    session_ws = _WORKSPACE_DIR / session_id
    if session_ws.is_dir():
        candidate = session_ws / file_path
        if candidate.is_file():
            try:
                return candidate.read_text(encoding="utf-8")
            except OSError:
                pass

    return None


# ---------------------------------------------------------------------------
# Prompt builders
# ---------------------------------------------------------------------------


def _build_fix_messages(
    bug_description: str,
    file_path: str,
    file_content: str,
    root_causes: list[dict],
) -> list[dict]:
    """Build the LLM messages for generating a fix for a single file."""
    system_prompt = (
        "You are an expert software engineer specialising in code repair. "
        "You will be given a bug description, the content of a Python source file, "
        "and the probable root causes identified by a prior analysis.\n"
        "Your task is to produce a concrete fix for the file.\n\n"
        "Respond ONLY with a valid JSON object matching this exact schema — no markdown, "
        "no commentary, no code fences:\n"
        '{\n'
        '  "fixes": [\n'
        '    {\n'
        '      "file_path": "<filename>",\n'
        '      "original": "<exact original code snippet to replace>",\n'
        '      "suggested": "<corrected code snippet>",\n'
        '      "explanation": "<one or two sentences explaining the change>"\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    # Truncate file content to stay within context limits.
    content_snippet = file_content[:_MAX_FILE_CHARS]

    # Summarise root causes relevant to this file.
    relevant_causes = [
        rc for rc in root_causes
        if rc.get("file", "") == file_path or rc.get("file", "") == ""
    ]
    causes_text = "\n".join(
        f"- {rc.get('description', '')} (line {rc.get('line_hint', '?')})"
        for rc in relevant_causes
    ) or "No specific root cause identified."

    user_content = (
        f"Generate a fix for the following bug.\n\n"
        f"Bug description:\n{bug_description}\n\n"
        f"Known issues in {file_path}:\n{causes_text}\n\n"
        f"=== {file_path} ===\n{content_snippet}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------


def generate_fixes(
    session_id: str,
    bug_description: str,
    project_id: str,
    analysis_result: dict,
    llm: LLMProvider,
) -> list[dict]:
    """
    Generate fix suggestions for files ranked above the confidence threshold.

    Args:
        session_id:       The session UUID.
        bug_description:  Free-text description of the bug.
        project_id:       Sample project id or 'upload' for uploaded files.
        analysis_result:  Dict with 'relevant_files' and 'root_causes' lists.
        llm:              LLMProvider instance (injected, never hardcoded).

    Returns:
        A list of fix dicts ready to be persisted to fix_suggestions.
        Each dict has: id, session_id, file_path, original, suggested, explanation.

    Raises:
        RuntimeError: Wraps any unexpected LLM error.
        ValueError:   If the LLM response is not valid JSON.
    """
    relevant_files: list[dict] = analysis_result.get("relevant_files", [])
    root_causes: list[dict] = analysis_result.get("root_causes", [])

    # Filter to files above the confidence threshold.
    high_confidence = [
        rf for rf in relevant_files
        if float(rf.get("confidence", 0)) > _CONFIDENCE_THRESHOLD
    ]

    fixes: list[dict] = []

    for rf in high_confidence:
        file_path: str = rf.get("path", "")
        if not file_path:
            continue

        file_content = _load_file_content(file_path, project_id, session_id)
        if file_content is None:
            logger.warning(
                "Session %s: could not load '%s'; skipping fix generation",
                session_id, file_path,
            )
            continue

        messages = _build_fix_messages(bug_description, file_path, file_content, root_causes)

        try:
            raw_response = llm.complete(messages, json_mode=True)
        except Exception as exc:
            logger.error(
                "LLM fix call failed for session %s, file %s: %s",
                session_id, file_path, exc,
            )
            raise LLMServiceError("LLM fix generation failed", exc) from exc

        try:
            payload = json.loads(raw_response)
        except (json.JSONDecodeError, ValueError) as exc:
            logger.error(
                "LLM returned invalid JSON for fix (session %s, file %s): %s",
                session_id, file_path, raw_response[:200],
            )
            raise LLMServiceError(f"LLM returned invalid JSON: {exc}", exc) from exc

        for fix in payload.get("fixes", []):
            if not isinstance(fix, dict):
                continue
            # Use the LLM-provided file_path if present, otherwise fall back
            # to the one we know is correct.
            resolved_path = fix.get("file_path") or file_path
            fixes.append(
                {
                    "id": str(uuid.uuid4()),
                    "session_id": session_id,
                    "file_path": str(resolved_path),
                    "original": str(fix.get("original", "")),
                    "suggested": str(fix.get("suggested", "")),
                    "explanation": str(fix.get("explanation", "")),
                }
            )

    return fixes
