"""
DevProof AI — Session Pydantic models (ST-4).

Matches the REST API contract Session / SessionCreate shapes exactly.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SessionStatus(str, Enum):
    created = "created"
    analyzed = "analyzed"
    fix_proposed = "fix_proposed"
    fix_approved = "fix_approved"
    fix_rejected = "fix_rejected"
    verified = "verified"


class SessionCreate(BaseModel):
    """Request body for POST /api/sessions."""

    project_id: str
    bug_description: str


class Session(BaseModel):
    """Response shape for GET/POST /api/sessions."""

    id: str
    project_id: str
    project_name: str
    bug_description: str
    status: SessionStatus
    created_at: str
