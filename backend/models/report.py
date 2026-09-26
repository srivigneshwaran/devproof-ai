"""
DevProof AI — Verification Report Pydantic models (ST-4).

Matches the REST API contract VerificationReport shape exactly.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel

from models.analysis import FileRelevance, RootCause
from models.fix import FixSuggestion


class GeneratedTest(BaseModel):
    """A single generated pytest test file."""

    file: str
    code: str


class VerificationReport(BaseModel):
    """Response shape for POST /api/verify and GET /api/report/{session_id}."""

    session_id: str
    project_name: str
    bug_description: str
    verdict: str                             # PASS | FAIL | PARTIAL | ERROR
    relevant_files: List[FileRelevance]
    root_causes: List[RootCause]
    fixes: List[FixSuggestion]
    tests_generated: List[GeneratedTest]
    test_output: str
    tests_passed: int
    tests_failed: int
    summary: str
    created_at: str
