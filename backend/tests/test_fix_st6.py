"""
Tests for ST-6: Fix Suggestion Service & Approval Workflow (Backend).

Covers:
- POST /api/fix — happy path (generates fixes, persists them, updates status)
- POST /api/fix — response shape matches FixList contract
- POST /api/fix — 404 for unknown session
- POST /api/fix — 404 when no analysis exists for session
- POST /api/fix — 503 when LLM fails
- GET /api/fix/{session_id} — returns persisted fixes
- GET /api/fix/{session_id} — 404 for unknown session
- GET /api/fix/{session_id} — 404 when no fixes generated yet
- GET /api/fix/{session_id} — data matches what POST produced
- POST /api/fix/{session_id}/approve — approved=True transitions to fix_approved
- POST /api/fix/{session_id}/approve — approved=False transitions to fix_rejected
- POST /api/fix/{session_id}/approve — developer feedback stored
- POST /api/fix/{session_id}/approve — no feedback (null) works fine
- POST /api/fix/{session_id}/approve — 409 if already approved
- POST /api/fix/{session_id}/approve — 409 if already rejected
- POST /api/fix/{session_id}/approve — 404 for unknown session
- POST /api/fix/{session_id}/approve — 404 when no fixes exist
- FixList shape: id, file_path, original, suggested, explanation required
- fix_service.generate_fixes() unit tests
- Regressions: ST-1 /health, ST-2 LLM, ST-3 projects, ST-4 schema, ST-5 analysis
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Force mock LLM for entire module
# ---------------------------------------------------------------------------
os.environ["LLM_PROVIDER"] = "mock"


# ---------------------------------------------------------------------------
# Shared FixList LLM response for test mocking
# ---------------------------------------------------------------------------
_MOCK_FIX_RESPONSE: dict = {
    "fixes": [
        {
            "file_path": "order_service.py",
            "original": "total = round((subtotal - discount_amount) * tax_rate, 2)",
            "suggested": "total = round(subtotal * tax_rate * (1 - discount_rate), 2)",
            "explanation": "Tax must be applied before discount.",
        }
    ]
}

_MOCK_ANALYSIS_RESPONSE: dict = {
    "relevant_files": [
        {"path": "order_service.py", "confidence": 0.94, "reason": "Discount logic"}
    ],
    "root_causes": [
        {"description": "Discount before tax", "file": "order_service.py", "line_hint": 27}
    ],
}


# ---------------------------------------------------------------------------
# DB seeding helpers
# ---------------------------------------------------------------------------

def _seed_analysis(session_id: str, relevant_files=None, root_causes=None) -> None:
    """
    Directly insert an analysis row into the DB with the given
    relevant_files/root_causes (default: single high-confidence file).
    Also updates the session status to 'analyzed'.
    """
    from db.database import get_connection

    if relevant_files is None:
        relevant_files = [
            {"path": "order_service.py", "confidence": 0.94, "reason": "Discount logic"}
        ]
    if root_causes is None:
        root_causes = [
            {"description": "Discount before tax", "file": "order_service.py", "line_hint": 27}
        ]

    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO analyses (id, session_id, relevant_files, root_causes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (analysis_id, session_id, json.dumps(relevant_files), json.dumps(root_causes), now),
        )
        conn.execute(
            "UPDATE sessions SET status = 'analyzed' WHERE id = ?",
            (session_id,),
        )


def _seed_fix(session_id: str) -> str:
    """
    Directly insert a fix_suggestions row into the DB.
    Also updates the session status to 'fix_proposed'.
    Returns the fix id.
    """
    from db.database import get_connection

    fix_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fix_suggestions
                (id, session_id, file_path, original, suggested, explanation, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fix_id,
                session_id,
                "order_service.py",
                "total = round((subtotal - discount_amount) * tax_rate, 2)",
                "total = round(subtotal * tax_rate * (1 - discount_rate), 2)",
                "Tax must be applied before discount.",
                now,
            ),
        )
        conn.execute(
            "UPDATE sessions SET status = 'fix_proposed' WHERE id = ?",
            (session_id,),
        )
    return fix_id


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """Shared FastAPI TestClient for the full application."""
    from fastapi.testclient import TestClient
    import main as app_module

    with TestClient(app_module.app) as c:
        yield c


@pytest.fixture()
def session_id(client):
    """Create a fresh session against the order_service project."""
    resp = client.post(
        "/api/sessions",
        json={
            "project_id": "order_service",
            "bug_description": "Discount applied before tax causing overcharge",
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture()
def analyzed_session_id(client, session_id):
    """
    Create a session and seed its analysis directly into the DB with a
    high-confidence file result so that fix generation reliably works
    regardless of the MockProvider keyword-matching heuristic.
    """
    _seed_analysis(session_id)
    return session_id


@pytest.fixture()
def fix_session_id(client, analyzed_session_id):
    """Create a session, seed analysis, generate fixes; return session_id."""
    resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
    assert resp.status_code == 200, resp.text
    return analyzed_session_id


@pytest.fixture()
def fix_seeded_session_id(client):
    """
    Create a session with analysis and fix directly seeded in DB.
    Used where we need a session with existing fixes without going through
    the full LLM path.
    """
    create_resp = client.post(
        "/api/sessions",
        json={
            "project_id": "order_service",
            "bug_description": "Direct seeded fix session",
        },
    )
    sid = create_resp.json()["id"]
    _seed_analysis(sid)
    _seed_fix(sid)
    return sid


# ===========================================================================
# POST /api/fix
# ===========================================================================


class TestGenerateFix:
    def test_returns_200(self, client, analyzed_session_id):
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        assert resp.status_code == 200

    def test_response_contains_session_id(self, client, analyzed_session_id):
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        assert resp.json()["session_id"] == analyzed_session_id

    def test_response_contains_fixes_list(self, client, analyzed_session_id):
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        data = resp.json()
        assert "fixes" in data
        assert isinstance(data["fixes"], list)

    def test_fix_list_shape(self, client, analyzed_session_id):
        """Each fix must have id, file_path, original, suggested, explanation."""
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        for fix in resp.json()["fixes"]:
            required = {"id", "file_path", "original", "suggested", "explanation"}
            assert required.issubset(set(fix.keys())), (
                f"Missing keys: {required - set(fix.keys())}"
            )

    def test_fix_id_is_uuid(self, client, analyzed_session_id):
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        for fix in resp.json()["fixes"]:
            uuid.UUID(fix["id"])  # raises if not a valid UUID

    def test_exact_top_level_keys(self, client, analyzed_session_id):
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        assert set(resp.json().keys()) == {"session_id", "fixes"}

    def test_session_status_updated_to_fix_proposed(self, client, analyzed_session_id):
        client.post("/api/fix", json={"session_id": analyzed_session_id})
        session_resp = client.get(f"/api/sessions/{analyzed_session_id}")
        assert session_resp.json()["status"] == "fix_proposed"

    def test_fixes_persisted_in_db(self, client, fix_session_id):
        """GET /api/fix/{session_id} succeeds after POST."""
        resp = client.get(f"/api/fix/{fix_session_id}")
        assert resp.status_code == 200

    def test_unknown_session_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post("/api/fix", json={"session_id": fake_id})
        assert resp.status_code == 404

    def test_missing_session_id_returns_422(self, client):
        resp = client.post("/api/fix", json={})
        assert resp.status_code == 422

    def test_no_analysis_returns_404(self, client):
        """A session with no analysis should return 404."""
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Bug with no analysis run",
            },
        )
        new_sid = create_resp.json()["id"]
        resp = client.post("/api/fix", json={"session_id": new_sid})
        assert resp.status_code == 404

    def test_llm_failure_returns_503(self, client):
        """When the LLM raises on a high-confidence analysis, the endpoint returns 503."""
        import main as app_module

        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "LLM failure test",
            },
        )
        sid = create_resp.json()["id"]
        # Seed high-confidence analysis so fix_service WILL call the LLM
        _seed_analysis(sid)

        # Temporarily replace the LLM with one that always fails.
        original_llm = app_module.app.state.llm
        failing_llm = MagicMock()
        failing_llm.complete.side_effect = Exception("Simulated LLM outage")
        app_module.app.state.llm = failing_llm

        try:
            resp = client.post("/api/fix", json={"session_id": sid})
            assert resp.status_code == 503
        finally:
            app_module.app.state.llm = original_llm

    def test_content_type_json(self, client, analyzed_session_id):
        resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        assert "application/json" in resp.headers["content-type"]


# ===========================================================================
# GET /api/fix/{session_id}
# ===========================================================================


class TestGetFixes:
    def test_returns_200_after_generate(self, client, fix_session_id):
        resp = client.get(f"/api/fix/{fix_session_id}")
        assert resp.status_code == 200

    def test_response_shape(self, client, fix_session_id):
        resp = client.get(f"/api/fix/{fix_session_id}")
        data = resp.json()
        assert set(data.keys()) == {"session_id", "fixes"}

    def test_session_id_in_response(self, client, fix_session_id):
        resp = client.get(f"/api/fix/{fix_session_id}")
        assert resp.json()["session_id"] == fix_session_id

    def test_fixes_list_not_empty(self, client, fix_session_id):
        resp = client.get(f"/api/fix/{fix_session_id}")
        assert isinstance(resp.json()["fixes"], list)
        # fix_session_id fixture calls POST /api/fix which inserts real fixes
        assert len(resp.json()["fixes"]) >= 1

    def test_fix_items_have_required_keys(self, client, fix_session_id):
        resp = client.get(f"/api/fix/{fix_session_id}")
        for fix in resp.json()["fixes"]:
            required = {"id", "file_path", "original", "suggested", "explanation"}
            assert required.issubset(set(fix.keys()))

    def test_data_matches_post_result(self, client, analyzed_session_id):
        """GET should return the same fixes as the POST that created them."""
        post_resp = client.post("/api/fix", json={"session_id": analyzed_session_id})
        post_fixes = post_resp.json()["fixes"]
        get_resp = client.get(f"/api/fix/{analyzed_session_id}")
        get_fixes = get_resp.json()["fixes"]
        # IDs should match (fixes are immutable after creation)
        post_ids = {f["id"] for f in post_fixes}
        get_ids = {f["id"] for f in get_fixes}
        assert post_ids == get_ids

    def test_404_for_unknown_session(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/fix/{fake_id}")
        assert resp.status_code == 404

    def test_404_when_no_fixes_generated(self, client):
        """A fresh analyzed session with no fixes yet returns 404."""
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "No fixes generated for this session",
            },
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        resp = client.get(f"/api/fix/{sid}")
        assert resp.status_code == 404

    def test_get_seeded_fix_returns_200(self, client, fix_seeded_session_id):
        """Directly seeded fix is returned by GET."""
        resp = client.get(f"/api/fix/{fix_seeded_session_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["fixes"]) == 1
        assert data["fixes"][0]["file_path"] == "order_service.py"


# ===========================================================================
# POST /api/fix/{session_id}/approve
# ===========================================================================


class TestApproveFix:
    def test_approve_returns_200(self, client, fix_seeded_session_id):
        resp = client.post(
            f"/api/fix/{fix_seeded_session_id}/approve",
            json={"approved": True},
        )
        assert resp.status_code == 200

    def test_approve_status_in_response(self, client, fix_seeded_session_id):
        resp = client.post(
            f"/api/fix/{fix_seeded_session_id}/approve",
            json={"approved": True},
        )
        assert resp.json()["status"] == "fix_approved"

    def test_session_status_updated_to_fix_approved(self, client, fix_seeded_session_id):
        client.post(
            f"/api/fix/{fix_seeded_session_id}/approve",
            json={"approved": True},
        )
        session_resp = client.get(f"/api/sessions/{fix_seeded_session_id}")
        assert session_resp.json()["status"] == "fix_approved"

    def test_reject_returns_200(self, client):
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Reject test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        resp = client.post(
            f"/api/fix/{sid}/approve",
            json={"approved": False},
        )
        assert resp.status_code == 200

    def test_reject_status_in_response(self, client):
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Reject status test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        resp = client.post(
            f"/api/fix/{sid}/approve",
            json={"approved": False},
        )
        assert resp.json()["status"] == "fix_rejected"

    def test_session_status_updated_to_fix_rejected(self, client):
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Reject session test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        client.post(f"/api/fix/{sid}/approve", json={"approved": False})
        session_resp = client.get(f"/api/sessions/{sid}")
        assert session_resp.json()["status"] == "fix_rejected"

    def test_reject_with_feedback_persisted(self, client):
        """Developer feedback is stored in fix_approvals."""
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Feedback persistence test",
            },
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)

        resp = client.post(
            f"/api/fix/{sid}/approve",
            json={"approved": False, "feedback": "The fix approach is incorrect."},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "fix_rejected"

        # Verify feedback was persisted in DB
        from db.database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT feedback FROM fix_approvals WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
                (sid,),
            ).fetchone()
        assert row is not None
        assert row["feedback"] == "The fix approach is incorrect."

    def test_approve_without_feedback_works(self, client):
        """Approval without feedback (null) must succeed."""
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "No feedback approve test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        resp = client.post(f"/api/fix/{sid}/approve", json={"approved": True})
        assert resp.status_code == 200

    def test_approval_persisted_in_fix_approvals_table(self, client):
        """fix_approvals row is created with correct approved value."""
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Approval persistence test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        client.post(f"/api/fix/{sid}/approve", json={"approved": True})

        from db.database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT approved FROM fix_approvals WHERE session_id = ?",
                (sid,),
            ).fetchone()
        assert row is not None
        assert row["approved"] == 1

    def test_null_feedback_stored_when_no_feedback_given(self, client):
        """When no feedback is provided, fix_approvals.feedback is NULL."""
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Null feedback test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        client.post(f"/api/fix/{sid}/approve", json={"approved": True})

        from db.database import get_connection
        with get_connection() as conn:
            row = conn.execute(
                "SELECT feedback FROM fix_approvals WHERE session_id = ?",
                (sid,),
            ).fetchone()
        assert row is not None
        assert row["feedback"] is None

    def test_already_approved_returns_409(self, client):
        """Cannot approve a session that was already approved."""
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Double approve test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        client.post(f"/api/fix/{sid}/approve", json={"approved": True})
        resp = client.post(f"/api/fix/{sid}/approve", json={"approved": True})
        assert resp.status_code == 409

    def test_already_rejected_returns_409(self, client):
        """Cannot reject a session that was already rejected."""
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Double reject test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)
        client.post(f"/api/fix/{sid}/approve", json={"approved": False, "feedback": "Bad fix"})
        resp = client.post(f"/api/fix/{sid}/approve", json={"approved": True})
        assert resp.status_code == 409

    def test_approve_unknown_session_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post(
            f"/api/fix/{fake_id}/approve",
            json={"approved": True},
        )
        assert resp.status_code == 404

    def test_approve_no_fixes_returns_404(self, client):
        """Cannot approve a session that has no fixes generated."""
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Approval without fixes test",
            },
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        # No fix seeded
        resp = client.post(
            f"/api/fix/{sid}/approve",
            json={"approved": True},
        )
        assert resp.status_code == 404

    def test_approve_missing_approved_field_returns_422(self, client, fix_seeded_session_id):
        resp = client.post(
            f"/api/fix/{fix_seeded_session_id}/approve",
            json={},
        )
        assert resp.status_code == 422


# ===========================================================================
# Approval workflow rules
# ===========================================================================


class TestApprovalWorkflowRules:
    def test_fix_not_approved_without_explicit_approve_call(self, client, fix_session_id):
        """Session must NOT be in fix_approved state just from generating fixes."""
        session_resp = client.get(f"/api/sessions/{fix_session_id}")
        # Should still be fix_proposed (not approved yet)
        assert session_resp.json()["status"] == "fix_proposed"

    def test_full_approval_workflow(self, client):
        """
        End-to-end approval workflow:
        create session → seed analysis → generate fixes → approve → status = fix_approved
        """
        # 1. Create session
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Full approval workflow test",
            },
        )
        assert create_resp.status_code == 201
        sid = create_resp.json()["id"]
        assert create_resp.json()["status"] == "created"

        # 2. Seed analysis with high-confidence file
        _seed_analysis(sid)
        session_after_analysis = client.get(f"/api/sessions/{sid}").json()
        assert session_after_analysis["status"] == "analyzed"

        # 3. Generate fixes via API (LLM is called here)
        fix_resp = client.post("/api/fix", json={"session_id": sid})
        assert fix_resp.status_code == 200
        session_after_fix = client.get(f"/api/sessions/{sid}").json()
        assert session_after_fix["status"] == "fix_proposed"

        # 4. Approve
        approve_resp = client.post(
            f"/api/fix/{sid}/approve",
            json={"approved": True},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "fix_approved"

        # 5. Session status final
        final_session = client.get(f"/api/sessions/{sid}").json()
        assert final_session["status"] == "fix_approved"

    def test_full_rejection_workflow(self, client):
        """
        End-to-end rejection workflow:
        create session → seed analysis → generate fixes → reject (with feedback) → fix_rejected
        """
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Full rejection workflow test",
            },
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)

        fix_resp = client.post("/api/fix", json={"session_id": sid})
        assert fix_resp.status_code == 200

        approve_resp = client.post(
            f"/api/fix/{sid}/approve",
            json={"approved": False, "feedback": "Not the right fix."},
        )
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "fix_rejected"

        final_session = client.get(f"/api/sessions/{sid}").json()
        assert final_session["status"] == "fix_rejected"

    def test_seeded_full_approval_workflow(self, client):
        """
        Full workflow using directly seeded DB state (no LLM call path).
        Verifies state transitions are correct independent of LLM mocking.
        """
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Seeded workflow test"},
        )
        sid = create_resp.json()["id"]
        _seed_analysis(sid)
        _seed_fix(sid)

        # Before approval: fix_proposed
        assert client.get(f"/api/sessions/{sid}").json()["status"] == "fix_proposed"

        # Approve
        approve_resp = client.post(f"/api/fix/{sid}/approve", json={"approved": True})
        assert approve_resp.status_code == 200
        assert approve_resp.json()["status"] == "fix_approved"

        # After: fix_approved
        assert client.get(f"/api/sessions/{sid}").json()["status"] == "fix_approved"

    def test_auth_service_fix_workflow(self, client):
        """Fix workflow also works for the auth_service sample project."""
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "auth_service",
                "bug_description": "Token not expiring at exact timestamp",
            },
        )
        assert create_resp.status_code == 201
        sid = create_resp.json()["id"]
        # Seed analysis for auth_service (auth.py)
        _seed_analysis(
            sid,
            relevant_files=[{"path": "auth.py", "confidence": 0.92, "reason": "Token expiry check"}],
            root_causes=[{"description": "Off-by-one in expiry check", "file": "auth.py", "line_hint": 15}],
        )
        fix_resp = client.post("/api/fix", json={"session_id": sid})
        assert fix_resp.status_code == 200
        assert fix_resp.json()["session_id"] == sid


# ===========================================================================
# fix_service unit tests
# ===========================================================================


class TestFixServiceUnit:
    """Unit tests for fix_service.generate_fixes() using a mock LLM."""

    def _mock_llm(self, response_dict=None):
        """Return a MagicMock that mimics LLMProvider.complete()."""
        mock = MagicMock()
        if response_dict is None:
            response_dict = _MOCK_FIX_RESPONSE
        mock.complete.return_value = json.dumps(response_dict)
        return mock

    def test_generate_fixes_returns_list(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        result = generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=_MOCK_ANALYSIS_RESPONSE,
            llm=llm,
        )
        assert isinstance(result, list)

    def test_generate_fixes_contains_required_fields(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        fixes = generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=_MOCK_ANALYSIS_RESPONSE,
            llm=llm,
        )
        for fix in fixes:
            required = {"id", "session_id", "file_path", "original", "suggested", "explanation"}
            assert required.issubset(set(fix.keys()))

    def test_generate_fixes_uses_json_mode(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=_MOCK_ANALYSIS_RESPONSE,
            llm=llm,
        )
        call_kwargs = llm.complete.call_args
        # json_mode=True must be passed
        assert call_kwargs.kwargs.get("json_mode") is True or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] is True
        )

    def test_generate_fixes_passes_messages_list(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=_MOCK_ANALYSIS_RESPONSE,
            llm=llm,
        )
        messages = llm.complete.call_args.args[0]
        assert isinstance(messages, list)
        assert len(messages) >= 2  # system + user

    def test_generate_fixes_skips_low_confidence_files(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        low_conf_analysis = {
            "relevant_files": [
                {"path": "order_service.py", "confidence": 0.3, "reason": "Low confidence"}
            ],
            "root_causes": [],
        }
        fixes = generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=low_conf_analysis,
            llm=llm,
        )
        # Low confidence file should be skipped; no LLM call
        assert llm.complete.call_count == 0
        assert fixes == []

    def test_generate_fixes_raises_llm_service_error_on_llm_failure(self):
        from llm.exceptions import LLMServiceError
        from services.fix_service import generate_fixes

        llm = MagicMock()
        llm.complete.side_effect = Exception("LLM unavailable")
        with pytest.raises(LLMServiceError, match="LLM fix generation failed"):
            generate_fixes(
                session_id="test-session",
                bug_description="Discount before tax",
                project_id="order_service",
                analysis_result=_MOCK_ANALYSIS_RESPONSE,
                llm=llm,
            )

    def test_generate_fixes_raises_llm_service_error_on_bad_json(self):
        from llm.exceptions import LLMServiceError
        from services.fix_service import generate_fixes

        llm = MagicMock()
        llm.complete.return_value = "not valid json {"
        with pytest.raises(LLMServiceError, match="invalid JSON"):
            generate_fixes(
                session_id="test-session",
                bug_description="Discount before tax",
                project_id="order_service",
                analysis_result=_MOCK_ANALYSIS_RESPONSE,
                llm=llm,
            )

    def test_generate_fixes_each_fix_has_uuid_id(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        fixes = generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=_MOCK_ANALYSIS_RESPONSE,
            llm=llm,
        )
        for fix in fixes:
            uuid.UUID(fix["id"])  # raises ValueError if not a valid UUID

    def test_generate_fixes_session_id_in_each_fix(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        fixes = generate_fixes(
            session_id="my-session-id",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result=_MOCK_ANALYSIS_RESPONSE,
            llm=llm,
        )
        for fix in fixes:
            assert fix["session_id"] == "my-session-id"

    def test_generate_fixes_empty_analysis_returns_empty_list(self):
        from services.fix_service import generate_fixes

        llm = self._mock_llm()
        fixes = generate_fixes(
            session_id="test-session",
            bug_description="Discount before tax",
            project_id="order_service",
            analysis_result={"relevant_files": [], "root_causes": []},
            llm=llm,
        )
        assert fixes == []
        assert llm.complete.call_count == 0

    def test_build_fix_messages_includes_bug_description(self):
        from services.fix_service import _build_fix_messages

        msgs = _build_fix_messages(
            "unique bug description here",
            "order_service.py",
            "def foo(): pass",
            [],
        )
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "unique bug description here" in user_msg["content"]

    def test_build_fix_messages_includes_file_content(self):
        from services.fix_service import _build_fix_messages

        msgs = _build_fix_messages(
            "a bug",
            "order_service.py",
            "def calculate(): return 42",
            [],
        )
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "def calculate(): return 42" in user_msg["content"]

    def test_build_fix_messages_has_system_prompt(self):
        from services.fix_service import _build_fix_messages

        msgs = _build_fix_messages("a bug", "f.py", "x = 1", [])
        system_msg = next(m for m in msgs if m["role"] == "system")
        assert "JSON" in system_msg["content"]

    def test_build_fix_messages_includes_file_path(self):
        from services.fix_service import _build_fix_messages

        msgs = _build_fix_messages("a bug", "order_service.py", "x = 1", [])
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "order_service.py" in user_msg["content"]

    def test_build_fix_messages_includes_fix_keyword(self):
        """User message must contain 'fix' so MockProvider routes correctly."""
        from services.fix_service import _build_fix_messages

        msgs = _build_fix_messages("a bug", "f.py", "x = 1", [])
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "fix" in user_msg["content"].lower()


# ===========================================================================
# Regression: ST-1 /health
# ===========================================================================


class TestRegressionST1:
    def test_health_endpoint_still_works(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["service"] == "devproof-ai"


# ===========================================================================
# Regression: ST-2 LLM provider
# ===========================================================================


class TestRegressionST2:
    def test_mock_provider_available(self):
        from llm.mock_provider import MockProvider
        from llm.base import LLMProvider
        assert issubclass(MockProvider, LLMProvider)

    def test_factory_returns_mock(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from llm.factory import get_provider
        from llm.mock_provider import MockProvider
        assert isinstance(get_provider(), MockProvider)

    def test_app_state_llm_is_mock(self, client):
        import main as app_module
        from llm.mock_provider import MockProvider
        assert isinstance(app_module.app.state.llm, MockProvider)

    def test_mock_provider_returns_fix_response_for_fix_prompt(self):
        from llm.mock_provider import MockProvider
        p = MockProvider()
        result = p.complete(
            [{"role": "user", "content": "generate a fix for this code"}],
            json_mode=True,
        )
        data = json.loads(result)
        assert "fixes" in data


# ===========================================================================
# Regression: ST-3 projects
# ===========================================================================


class TestRegressionST3:
    def test_get_projects_200(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200

    def test_order_service_files_200(self, client):
        resp = client.get("/api/projects/order_service/files")
        assert resp.status_code == 200

    def test_upload_endpoint_reachable(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("test.py", io.BytesIO(b"x=1"), "text/x-python"))],
        )
        assert resp.status_code == 200

    def test_sample_project_files_still_on_disk(self):
        base = Path(__file__).resolve().parent.parent / "sample_projects"
        assert (base / "order_service" / "order_service.py").is_file()
        assert (base / "auth_service" / "auth.py").is_file()


# ===========================================================================
# Regression: ST-4 schema
# ===========================================================================


class TestRegressionST4:
    def test_fix_suggestions_table_exists(self):
        from db.database import get_connection, DB_PATH
        if DB_PATH.exists():
            conn = get_connection()
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            conn.close()
            assert "fix_suggestions" in tables
            assert "fix_approvals" in tables

    def test_fix_models_importable(self):
        from models.fix import FixSuggestion, FixList, FixApproval
        fl = FixList(
            session_id="s",
            fixes=[
                FixSuggestion(
                    id="fix-1",
                    file_path="f.py",
                    original="a",
                    suggested="b",
                    explanation="e",
                )
            ],
        )
        assert fl.session_id == "s"

    def test_fix_approval_model(self):
        from models.fix import FixApproval
        fa = FixApproval(approved=True, feedback="Looks good")
        assert fa.approved is True
        assert fa.feedback == "Looks good"


# ===========================================================================
# Regression: ST-5 analysis endpoints
# ===========================================================================


class TestRegressionST5:
    def test_analysis_endpoint_still_works(self, client):
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "ST-5 regression check",
            },
        )
        sid = create_resp.json()["id"]
        analysis_resp = client.post("/api/analysis", json={"session_id": sid})
        assert analysis_resp.status_code == 200
        data = analysis_resp.json()
        assert "relevant_files" in data
        assert "root_causes" in data

    def test_get_analysis_still_works(self, client):
        create_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "auth_service",
                "bug_description": "ST-5 regression GET check",
            },
        )
        sid = create_resp.json()["id"]
        client.post("/api/analysis", json={"session_id": sid})
        get_resp = client.get(f"/api/analysis/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["session_id"] == sid

    def test_sessions_crud_still_works(self, client):
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "regression check"},
        )
        assert create_resp.status_code == 201
        sid = create_resp.json()["id"]
        get_resp = client.get(f"/api/sessions/{sid}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == sid

    def test_sessions_list_still_works(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
