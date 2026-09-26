"""
DevProof AI — Analysis Pydantic models (ST-4).

Matches the REST API contract AnalysisResult shape exactly.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class FileRelevance(BaseModel):
    """A single file ranked by relevance to the bug."""

    path: str
    confidence: float
    reason: str


class RootCause(BaseModel):
    """A probable root cause linked to a file."""

    description: str
    file: str
    line_hint: Optional[int] = None


class AnalysisResult(BaseModel):
    """Response shape for POST /api/analysis and GET /api/analysis/{session_id}."""

    session_id: str
    relevant_files: List[FileRelevance]
    root_causes: List[RootCause]
