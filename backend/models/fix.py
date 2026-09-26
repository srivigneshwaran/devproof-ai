"""
DevProof AI — Fix Suggestion Pydantic models (ST-4).

Matches the REST API contract FixList / FixSuggestion / FixApproval shapes exactly.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class FixSuggestion(BaseModel):
    """A single file-level fix suggestion."""

    id: str
    file_path: str
    original: str
    suggested: str
    explanation: str


class FixList(BaseModel):
    """Response shape for POST /api/fix and GET /api/fix/{session_id}."""

    session_id: str
    fixes: List[FixSuggestion]


class FixApproval(BaseModel):
    """Request body for POST /api/fix/{session_id}/approve."""

    approved: bool
    feedback: Optional[str] = None
