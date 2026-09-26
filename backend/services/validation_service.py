"""
DevProof AI — Validation Service (ST-7).

Runs a controlled pytest execution inside the session workspace and collects
the results.

    run_tests(session_id, generated_tests, fixes) -> dict

Security constraints (from devproof-ai-plan.md ST-7 and ST-9):
  - cwd always set to the resolved backend/workspace/{session_id}/ directory
  - Subprocess uses list form, never shell=True
  - Hard 30-second timeout
  - Path traversal guard: assert resolved path starts with WORKSPACE_ROOT
  - The workspace path is never derived from user input or LLM output
  - Pytest executable is the one from the venv, located by sys.executable
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).resolve().parent.parent
_WORKSPACE_ROOT = _BACKEND_DIR / "workspace"
_SAMPLE_PROJECTS_DIR = _BACKEND_DIR / "sample_projects"

# Subprocess timeout in seconds
_PYTEST_TIMEOUT = 30


def _resolve_workspace(session_id: str) -> Path:
    """
    Resolve the workspace path for *session_id* and enforce that it stays
    within WORKSPACE_ROOT (path traversal guard).

    Raises:
        ValueError: If the resolved path escapes WORKSPACE_ROOT.
    """
    # session_id must not contain path separators or special sequences.
    # We construct the path from a trusted root; resolve() collapses any
    # traversal sequences that might slip in.
    candidate = (_WORKSPACE_ROOT / session_id).resolve()

    # Guard: resolved path MUST be a direct child of WORKSPACE_ROOT.
    try:
        candidate.relative_to(_WORKSPACE_ROOT.resolve())
    except ValueError:
        raise ValueError(
            f"Path traversal detected: '{session_id}' escapes the workspace root."
        )

    return candidate


def _ensure_workspace(session_id: str) -> Path:
    """Create the workspace directory for *session_id* if it does not exist."""
    ws = _resolve_workspace(session_id)
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _copy_source_files(session_id: str, project_id: str, workspace_dir: Path) -> None:
    """
    Seed the workspace with the source files for *project_id*.

    For sample projects, copies the .py files from sample_projects/{project_id}/
    into the workspace (skipping files that already exist there).
    For uploaded projects the files are already in the workspace.
    """
    if project_id == "upload":
        # Files uploaded by the user are already in the workspace; nothing to do.
        return

    source_dir = _SAMPLE_PROJECTS_DIR / project_id
    if not source_dir.is_dir():
        logger.warning("Source project dir not found: %s", source_dir)
        return

    for py_file in source_dir.glob("*.py"):
        dest = workspace_dir / py_file.name
        if not dest.exists():
            shutil.copy2(str(py_file), str(dest))


def _apply_fix(
    workspace_dir: Path,
    file_path: str,
    original: str,
    suggested: str,
) -> None:
    """
    Apply the fix to the workspace source file by replacing the *original*
    snippet with the *suggested* snippet.

    *file_path* is a bare filename (e.g. "order_service.py") — never a path
    with directory components.  Only the workspace directory is ever written.

    Strategy:
    - If the target file exists and contains the original snippet,
      replace it with the suggested snippet (targeted in-place replacement).
    - If the target file exists but does not contain the original snippet
      verbatim, the file is left unchanged (fix already applied or mismatch).
    - If the target file does not exist, write the suggested content as the
      entire file content (handles the case where only a snippet was provided).

    Raises:
        ValueError: If file_path contains path separators or escapes the workspace.
    """
    # Validate: file_path must be a simple filename, never a relative path
    # with directory components that could escape the workspace.
    safe_name = Path(file_path).name  # strips any directory prefix
    if safe_name != file_path or "/" in file_path or "\\" in file_path:
        raise ValueError(
            f"fix file_path must be a plain filename, got: '{file_path}'"
        )

    target = workspace_dir / safe_name
    # Belt-and-suspenders: ensure target resolves inside workspace_dir.
    if not str(target.resolve()).startswith(str(workspace_dir.resolve())):
        raise ValueError(
            f"Path traversal detected in fix file_path: '{file_path}'"
        )

    if target.is_file():
        existing = target.read_text(encoding="utf-8")
        if original and original in existing:
            # Targeted replacement: swap the buggy snippet for the fixed one.
            patched = existing.replace(original, suggested, 1)
            target.write_text(patched, encoding="utf-8")
        # If original snippet not found, leave the file as-is.
        # (The fix may already be applied, or the snippet doesn't match exactly.)
    else:
        # File not seeded yet — write the suggested code.
        target.write_text(suggested, encoding="utf-8")


def _write_test_files(workspace_dir: Path, generated_tests: list[dict]) -> list[Path]:
    """
    Write generated test files into the workspace.

    Returns the list of written paths so they can be cleaned up after the run.

    Raises:
        ValueError: If a test filename contains directory separators.
    """
    written: list[Path] = []
    for test in generated_tests:
        filename: str = test.get("file", "")
        code: str = test.get("code", "")

        # Validate: filename must be a simple name with no path components.
        safe_name = Path(filename).name
        if safe_name != filename or "/" in filename or "\\" in filename:
            raise ValueError(
                f"Test filename must be a plain filename, got: '{filename}'"
            )

        # Only .py files allowed.
        if not safe_name.endswith(".py"):
            raise ValueError(
                f"Test file must have a .py extension, got: '{filename}'"
            )

        dest = workspace_dir / safe_name
        dest.write_text(code, encoding="utf-8")
        written.append(dest)

    return written


def _parse_pytest_output(stdout: str, stderr: str) -> dict:
    """
    Parse the pytest summary line from stdout/stderr to extract pass/fail counts.

    Returns a dict: {tests_passed: int, tests_failed: int, tests_errored: int}
    """
    combined = stdout + "\n" + stderr

    # Look for the summary line, e.g.:
    #   "3 passed in 0.21s"
    #   "1 passed, 2 failed in 0.30s"
    #   "3 failed in 0.10s"
    #   "5 error in 0.05s"

    passed = 0
    failed = 0
    errored = 0

    passed_match = re.search(r"(\d+)\s+passed", combined)
    if passed_match:
        passed = int(passed_match.group(1))

    failed_match = re.search(r"(\d+)\s+failed", combined)
    if failed_match:
        failed = int(failed_match.group(1))

    error_match = re.search(r"(\d+)\s+error", combined)
    if error_match:
        errored = int(error_match.group(1))

    return {
        "tests_passed": passed,
        "tests_failed": failed,
        "tests_errored": errored,
    }


def run_tests(
    session_id: str,
    generated_tests: list[dict],
    fixes: list[dict],
    project_id: str,
) -> dict:
    """
    Apply the approved fix to the workspace, write generated tests, run pytest,
    collect results, and clean up test files.

    Args:
        session_id:      Session UUID — determines the workspace directory.
        generated_tests: List of {"file": str, "code": str} dicts.
        fixes:           List of fix dicts with file_path and suggested fields.
        project_id:      Sample project id or 'upload'.

    Returns:
        A dict with keys:
            tests_passed  (int)
            tests_failed  (int)
            tests_errored (int)
            test_output   (str)   — combined pytest stdout + stderr (truncated)
            exit_code     (int)   — pytest process exit code
            timed_out     (bool)  — True if subprocess timed out

    Security:
        - workspace path resolved and validated against WORKSPACE_ROOT
        - subprocess uses list form, shell=False, cwd=workspace_dir
        - 30-second timeout enforced
        - Only .py files written into workspace
        - pytest is invoked as "python -m pytest" using sys.executable (venv python)
    """
    # Step 1: Resolve and validate workspace path.
    workspace_dir = _ensure_workspace(session_id)

    # Step 2: Seed source files into workspace (for sample projects).
    _copy_source_files(session_id, project_id, workspace_dir)

    # Step 3: Apply fixes — replace original snippet with suggested snippet.
    for fix in fixes:
        file_path: str = fix.get("file_path", "")
        original: str = fix.get("original", "")
        suggested: str = fix.get("suggested", "")
        if not file_path or not suggested:
            continue
        try:
            _apply_fix(workspace_dir, file_path, original, suggested)
        except ValueError as exc:
            logger.error(
                "Fix application failed for session %s, file %s: %s",
                session_id, file_path, exc,
            )
            return {
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_errored": 1,
                "test_output": f"Fix application error: {exc}",
                "exit_code": -1,
                "timed_out": False,
            }

    # Step 4: Write test files into workspace.
    test_file_paths: list[Path] = []
    try:
        test_file_paths = _write_test_files(workspace_dir, generated_tests)
    except ValueError as exc:
        logger.error(
            "Test file write error for session %s: %s", session_id, exc,
        )
        return {
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_errored": 1,
            "test_output": f"Test file write error: {exc}",
            "exit_code": -1,
            "timed_out": False,
        }

    if not test_file_paths:
        return {
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_errored": 0,
            "test_output": "No test files were generated.",
            "exit_code": 5,  # pytest exit code 5 = no tests collected
            "timed_out": False,
        }

    # Step 5: Run pytest in the controlled workspace.
    # Use sys.executable so we use the same venv Python that's running us.
    # List form with shell=False prevents shell injection.
    cmd = [
        sys.executable, "-m", "pytest",
        ".",
        "-v",
        "--tb=short",
        "--no-header",
    ]

    timed_out = False
    stdout_text = ""
    stderr_text = ""
    exit_code = -1

    try:
        result = subprocess.run(
            cmd,
            cwd=str(workspace_dir),  # Always the validated workspace path
            capture_output=True,
            text=True,
            timeout=_PYTEST_TIMEOUT,
            shell=False,  # Never shell=True
        )
        stdout_text = result.stdout or ""
        stderr_text = result.stderr or ""
        exit_code = result.returncode
    except subprocess.TimeoutExpired:
        logger.warning("pytest timed out for session %s", session_id)
        timed_out = True
        stdout_text = ""
        stderr_text = f"Test execution timed out after {_PYTEST_TIMEOUT}s"
        exit_code = -1

    # Step 6: Clean up test files from workspace (leave source files).
    for tp in test_file_paths:
        try:
            tp.unlink(missing_ok=True)
        except OSError as exc:
            logger.warning("Could not remove test file %s: %s", tp, exc)

    # Step 7: Parse results.
    combined_output = (stdout_text + "\n" + stderr_text).strip()
    # Truncate to 8 KB to avoid bloating the DB.
    if len(combined_output) > 8192:
        combined_output = combined_output[:8192] + "\n... (truncated)"

    counts = _parse_pytest_output(stdout_text, stderr_text)

    return {
        "tests_passed": counts["tests_passed"],
        "tests_failed": counts["tests_failed"],
        "tests_errored": counts["tests_errored"],
        "test_output": combined_output,
        "exit_code": exit_code,
        "timed_out": timed_out,
    }
