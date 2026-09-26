"""
DevProof AI — Report Service (ST-7).

Compiles a VerificationReport from pytest results, generates an LLM summary,
and persists everything to the reports table.

    compile_report(session_id, validation_result, generated_tests, fixes,
                   analysis_result, session_row, llm) -> VerificationReport

All LLM calls go through the LLMProvider.complete() abstraction — no direct
SDK usage.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from db.database import get_connection
from llm.base import LLMProvider
from models.analysis import FileRelevance, RootCause
from models.fix import FixSuggestion
from models.report import GeneratedTest, VerificationReport

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Verdict computation
# ---------------------------------------------------------------------------


def _compute_verdict(
    tests_passed: int,
    tests_failed: int,
    tests_errored: int,
    timed_out: bool,
    exit_code: int,
) -> str:
    """
    Compute the verification verdict from pytest results.

    Rules:
        ERROR   — subprocess timed out, or no tests were collected (exit_code 5),
                  or there were errors during collection/execution
        PASS    — all tests passed (failed == 0, errored == 0, passed > 0)
        FAIL    — all results are failures (passed == 0, failed > 0 OR errored > 0)
        PARTIAL — some passed and some failed/errored
    """
    if timed_out:
        return "ERROR"
    if exit_code == 5:
        # pytest exit code 5 = no tests were collected
        return "ERROR"
    if tests_errored > 0 and tests_passed == 0 and tests_failed == 0:
        return "ERROR"
    if tests_errored > 0 or tests_failed > 0:
        if tests_passed == 0:
            return "FAIL"
        return "PARTIAL"
    if tests_passed > 0 and tests_failed == 0 and tests_errored == 0:
        return "PASS"
    # Fallback: no tests collected successfully
    return "ERROR"


# ---------------------------------------------------------------------------
# LLM summary generation
# ---------------------------------------------------------------------------


def _build_summary_messages(
    bug_description: str,
    verdict: str,
    tests_passed: int,
    tests_failed: int,
    test_output: str,
) -> list[dict]:
    """Build the LLM messages to generate a 2-3 sentence summary."""
    system_prompt = (
        "You are a technical documentation expert. "
        "Write a concise 2-3 sentence summary of a software verification result. "
        "Be specific about what was fixed, how many tests ran, and what the verdict means. "
        "Respond with plain text only — no markdown, no bullet points."
    )

    # Truncate test output to avoid bloating the prompt.
    output_snippet = test_output[:800] if test_output else "(no output)"

    user_content = (
        f"Bug description: {bug_description}\n\n"
        f"Verdict: {verdict}\n"
        f"Tests passed: {tests_passed}\n"
        f"Tests failed: {tests_failed}\n\n"
        f"Pytest output (excerpt):\n{output_snippet}\n\n"
        "Write a 2-3 sentence summary of this verification result."
    )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]


def _generate_summary(
    session_id: str,
    bug_description: str,
    verdict: str,
    tests_passed: int,
    tests_failed: int,
    test_output: str,
    llm: LLMProvider,
) -> str:
    """
    Generate a 2-3 sentence LLM summary.  On failure, return a fallback string.
    """
    messages = _build_summary_messages(
        bug_description, verdict, tests_passed, tests_failed, test_output
    )
    try:
        summary = llm.complete(messages, json_mode=False)
        return summary.strip()
    except Exception as exc:
        logger.warning(
            "LLM summary generation failed for session %s: %s", session_id, exc
        )
        return (
            f"Verification completed with verdict {verdict}. "
            f"{tests_passed} test(s) passed, {tests_failed} test(s) failed."
        )


# ---------------------------------------------------------------------------
# Main service function
# ---------------------------------------------------------------------------


def compile_report(
    session_id: str,
    validation_result: dict,
    generated_tests: list[dict],
    fixes: list[dict],
    analysis_result: dict,
    project_name: str,
    bug_description: str,
    llm: LLMProvider,
) -> VerificationReport:
    """
    Compile a VerificationReport from pytest results and persist it.

    Args:
        session_id:        Session UUID.
        validation_result: Output dict from validation_service.run_tests().
        generated_tests:   List of {"file": str, "code": str} from test_service.
        fixes:             List of fix dicts (file_path, original, suggested, explanation).
        analysis_result:   Dict with relevant_files and root_causes lists.
        project_name:      Human-readable project name.
        bug_description:   Free-text bug description.
        llm:               LLMProvider instance.

    Returns:
        VerificationReport Pydantic model.
    """
    tests_passed: int = validation_result.get("tests_passed", 0)
    tests_failed: int = validation_result.get("tests_failed", 0)
    tests_errored: int = validation_result.get("tests_errored", 0)
    test_output: str = validation_result.get("test_output", "")
    exit_code: int = validation_result.get("exit_code", -1)
    timed_out: bool = validation_result.get("timed_out", False)

    # Compute verdict.
    verdict = _compute_verdict(
        tests_passed, tests_failed, tests_errored, timed_out, exit_code
    )

    # Generate summary via LLM.
    summary = _generate_summary(
        session_id=session_id,
        bug_description=bug_description,
        verdict=verdict,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        test_output=test_output,
        llm=llm,
    )

    # Build Pydantic model objects from raw dicts.
    relevant_files = [
        FileRelevance(**rf)
        for rf in analysis_result.get("relevant_files", [])
        if isinstance(rf, dict)
    ]
    root_causes = [
        RootCause(**rc)
        for rc in analysis_result.get("root_causes", [])
        if isinstance(rc, dict)
    ]
    fix_suggestions = [
        FixSuggestion(
            id=f.get("id", str(uuid.uuid4())),
            file_path=f.get("file_path", ""),
            original=f.get("original", ""),
            suggested=f.get("suggested", ""),
            explanation=f.get("explanation", ""),
        )
        for f in fixes
        if isinstance(f, dict)
    ]
    test_objects = [
        GeneratedTest(file=t.get("file", ""), code=t.get("code", ""))
        for t in generated_tests
        if isinstance(t, dict)
    ]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report_id = str(uuid.uuid4())

    # Persist to DB.
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO reports
                (id, session_id, tests_generated, test_output,
                 tests_passed, tests_failed, verdict, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                session_id,
                json.dumps([t.model_dump() for t in test_objects]),
                test_output,
                tests_passed,
                tests_failed,
                verdict,
                summary,
                now,
            ),
        )
        conn.execute(
            "UPDATE sessions SET status = 'verified' WHERE id = ?",
            (session_id,),
        )

    return VerificationReport(
        session_id=session_id,
        project_name=project_name,
        bug_description=bug_description,
        verdict=verdict,
        relevant_files=relevant_files,
        root_causes=root_causes,
        fixes=fix_suggestions,
        tests_generated=test_objects,
        test_output=test_output,
        tests_passed=tests_passed,
        tests_failed=tests_failed,
        summary=summary,
        created_at=now,
    )
