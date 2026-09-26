"""
DevProof AI — Test Generation Service (ST-7).

Generates pytest test code from the approved fix using the LLMProvider abstraction.

    generate_tests(session_id, fixes, analysis_result, bug_description, llm) -> list[dict]

Each returned dict has:
    file: str   — filename for the test file (e.g. "test_order_service.py")
    code: str   — complete, runnable pytest source code

All LLM calls go through the LLMProvider.complete() abstraction — no direct
SDK usage.
"""

from __future__ import annotations

import logging
import re

from llm.base import LLMProvider

logger = logging.getLogger(__name__)

# Markdown code-fence pattern to strip from LLM output.
_CODE_FENCE_RE = re.compile(
    r"^```(?:python)?\s*\n(.*?)\n```\s*$",
    re.DOTALL | re.MULTILINE,
)


def _strip_code_fences(text: str) -> str:
    """
    Remove leading/trailing markdown code fences from *text*.

    If the text is wrapped in a single ``` block, extract just the code.
    Otherwise return the text unchanged (some providers don't add fences).
    """
    text = text.strip()
    match = _CODE_FENCE_RE.search(text)
    if match:
        return match.group(1).strip()
    # Also handle a plain ``` fence with no language tag
    plain_fence = re.compile(r"^```\s*\n(.*?)\n```\s*$", re.DOTALL)
    m = plain_fence.search(text)
    if m:
        return m.group(1).strip()
    return text


def _build_test_messages(
    bug_description: str,
    file_path: str,
    original: str,
    suggested: str,
    explanation: str,
) -> list[dict]:
    """
    Build the LLM messages to generate pytest tests for a single fix.
    """
    # Derive a test filename from the source filename.
    base = file_path.replace(".py", "")
    test_filename = f"test_{base}.py"

    system_prompt = (
        "You are an expert Python test engineer. "
        "You will be given a bug description and a code fix (original → suggested). "
        "Write a complete, self-contained pytest test file that verifies the fix is correct. "
        "The tests must import the module using the filename without path prefix "
        f"(e.g. `from {base} import ...`). "
        "Write at least 3 focused test functions. "
        "Do NOT use mocks or patches — call the real functions directly. "
        "Return ONLY valid Python source code with no markdown code fences, "
        "no commentary, and no extra text outside the code."
    )

    user_content = (
        f"Bug description:\n{bug_description}\n\n"
        f"File: {file_path}\n\n"
        f"Original (buggy) code snippet:\n{original}\n\n"
        f"Suggested (fixed) code snippet:\n{suggested}\n\n"
        f"Fix explanation:\n{explanation}\n\n"
        f"Write a pytest test file that will pass when the fixed code is in place "
        f"and would fail against the buggy code. "
        f"Save the test file as: {test_filename}"
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def generate_tests(
    session_id: str,
    fixes: list[dict],
    bug_description: str,
    llm: LLMProvider,
) -> list[dict]:
    """
    Generate pytest test code for each approved fix.

    Args:
        session_id:      The session UUID (used for logging).
        fixes:           List of fix dicts with file_path, original, suggested, explanation.
        bug_description: Free-text bug description.
        llm:             LLMProvider instance (never hardcoded).

    Returns:
        A list of dicts: [{"file": "<test filename>", "code": "<pytest source>"}]

    Raises:
        RuntimeError: Wraps any LLM failure.
    """
    tests: list[dict] = []

    for fix in fixes:
        file_path: str = fix.get("file_path", "")
        if not file_path:
            continue

        base = file_path.replace(".py", "")
        test_filename = f"test_{base}.py"

        messages = _build_test_messages(
            bug_description=bug_description,
            file_path=file_path,
            original=fix.get("original", ""),
            suggested=fix.get("suggested", ""),
            explanation=fix.get("explanation", ""),
        )

        try:
            raw_response = llm.complete(messages, json_mode=False)
        except Exception as exc:
            logger.error(
                "LLM test generation failed for session %s, file %s: %s",
                session_id, file_path, exc,
            )
            raise RuntimeError(f"LLM test generation failed: {exc}") from exc

        code = _strip_code_fences(raw_response)
        tests.append({"file": test_filename, "code": code})

    return tests
