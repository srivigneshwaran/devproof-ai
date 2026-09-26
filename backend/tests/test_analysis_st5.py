"""
Tests for ST-5: Analysis & Root-Cause Service (Backend).

Covers:
- Sessions CRUD: POST, GET (list), GET (by id)
- POST /api/sessions input validation
- POST /api/analysis — happy path (sample project)
- POST /api/analysis — persists result and updates session status
- POST /api/analysis — returns correct AnalysisResult shape
- POST /api/analysis — 404 for unknown session
- GET /api/analysis/{session_id} — returns persisted result
- GET /api/analysis/{session_id} — 404 when no analysis exists
- GET /api/analysis/{session_id} — 404 when session does not exist
- analysis_service.analyze() unit tests
- Regressions: ST-1 /health, ST-2 LLM factory, ST-3 projects, ST-4 schema
"""

from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import uuid
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# ---------------------------------------------------------------------------
# Environment: force mock LLM for entire module
# ---------------------------------------------------------------------------
os.environ["LLM_PROVIDER"] = "mock"


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
    """Create a fresh session against the order_service project and return its id."""
    resp = client.post(
        "/api/sessions",
        json={"project_id": "order_service", "bug_description": "Discount applied before tax causing overcharge"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


@pytest.fixture()
def analyzed_session_id(client, session_id):
    """Create a session and run analysis on it, return session_id."""
    resp = client.post("/api/analysis", json={"session_id": session_id})
    assert resp.status_code == 200, resp.text
    return session_id


# ===========================================================================
# Session router tests
# ===========================================================================


class TestCreateSession:
    def test_returns_201(self, client):
        resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Discount is applied before tax",
            },
        )
        assert resp.status_code == 201

    def test_response_shape(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Bug in discount calc"},
        )
        data = resp.json()
        required_keys = {"id", "project_id", "project_name", "bug_description", "status", "created_at"}
        assert required_keys.issubset(set(data.keys()))

    def test_status_is_created(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Bug in discount calc"},
        )
        assert resp.json()["status"] == "created"

    def test_project_name_populated(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Bug in discount calc"},
        )
        assert resp.json()["project_name"] == "Order Service"

    def test_id_is_uuid(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Bug in discount calc"},
        )
        sid = resp.json()["id"]
        # Should parse as UUID without raising
        uuid.UUID(sid)

    def test_project_id_stored_correctly(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Bug in discount calc"},
        )
        assert resp.json()["project_id"] == "order_service"

    def test_auth_service_session(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "auth_service", "bug_description": "Token not expiring correctly"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["project_id"] == "auth_service"
        assert data["project_name"] == "Auth Service"

    def test_upload_sentinel_accepted(self, client):
        """project_id='upload' must be accepted without 404."""
        resp = client.post(
            "/api/sessions",
            json={"project_id": "upload", "bug_description": "Division by zero in my uploaded code"},
        )
        assert resp.status_code == 201
        assert resp.json()["project_id"] == "upload"
        assert resp.json()["project_name"] == "Uploaded Files"

    def test_unknown_project_id_returns_404(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "nonexistent_xyz", "bug_description": "Some bug description here"},
        )
        assert resp.status_code == 404

    def test_missing_project_id_returns_422(self, client):
        resp = client.post(
            "/api/sessions",
            json={"bug_description": "Some bug"},
        )
        assert resp.status_code == 422

    def test_missing_bug_description_returns_422(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service"},
        )
        assert resp.status_code == 422


class TestListSessions:
    def test_returns_200(self, client):
        resp = client.get("/api/sessions")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        resp = client.get("/api/sessions")
        assert isinstance(resp.json(), list)

    def test_session_shape_in_list(self, client, session_id):
        resp = client.get("/api/sessions")
        sessions = resp.json()
        # Find our session
        found = next((s for s in sessions if s["id"] == session_id), None)
        assert found is not None
        required_keys = {"id", "project_id", "project_name", "bug_description", "status", "created_at"}
        assert required_keys.issubset(set(found.keys()))


class TestGetSession:
    def test_returns_200(self, client, session_id):
        resp = client.get(f"/api/sessions/{session_id}")
        assert resp.status_code == 200

    def test_returns_correct_session(self, client, session_id):
        resp = client.get(f"/api/sessions/{session_id}")
        assert resp.json()["id"] == session_id

    def test_unknown_session_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/sessions/{fake_id}")
        assert resp.status_code == 404

    def test_content_type_json(self, client, session_id):
        resp = client.get(f"/api/sessions/{session_id}")
        assert "application/json" in resp.headers["content-type"]


# ===========================================================================
# Analysis router tests
# ===========================================================================


class TestRunAnalysis:
    def test_post_returns_200(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        assert resp.status_code == 200

    def test_response_contains_session_id(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        assert resp.json()["session_id"] == session_id

    def test_response_contains_relevant_files(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        data = resp.json()
        assert "relevant_files" in data
        assert isinstance(data["relevant_files"], list)

    def test_response_contains_root_causes(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        data = resp.json()
        assert "root_causes" in data
        assert isinstance(data["root_causes"], list)

    def test_relevant_files_shape(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        for rf in resp.json()["relevant_files"]:
            assert "path" in rf
            assert "confidence" in rf
            assert "reason" in rf
            assert isinstance(rf["confidence"], float)

    def test_root_causes_shape(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        for rc in resp.json()["root_causes"]:
            assert "description" in rc
            assert "file" in rc
            # line_hint is optional (may be None)
            assert "line_hint" in rc

    def test_session_status_updated_to_analyzed(self, client, session_id):
        client.post("/api/analysis", json={"session_id": session_id})
        session_resp = client.get(f"/api/sessions/{session_id}")
        assert session_resp.json()["status"] == "analyzed"

    def test_result_persisted_in_db(self, client, analyzed_session_id):
        """GET /api/analysis/{session_id} should succeed after POST."""
        resp = client.get(f"/api/analysis/{analyzed_session_id}")
        assert resp.status_code == 200

    def test_unknown_session_returns_404(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.post("/api/analysis", json={"session_id": fake_id})
        assert resp.status_code == 404

    def test_missing_session_id_returns_422(self, client):
        resp = client.post("/api/analysis", json={})
        assert resp.status_code == 422

    def test_exact_response_keys(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        data = resp.json()
        assert set(data.keys()) == {"session_id", "relevant_files", "root_causes"}

    def test_content_type_json(self, client, session_id):
        resp = client.post("/api/analysis", json={"session_id": session_id})
        assert "application/json" in resp.headers["content-type"]


class TestGetAnalysis:
    def test_returns_200_after_analysis(self, client, analyzed_session_id):
        resp = client.get(f"/api/analysis/{analyzed_session_id}")
        assert resp.status_code == 200

    def test_response_shape(self, client, analyzed_session_id):
        resp = client.get(f"/api/analysis/{analyzed_session_id}")
        data = resp.json()
        assert set(data.keys()) == {"session_id", "relevant_files", "root_causes"}

    def test_session_id_in_response(self, client, analyzed_session_id):
        resp = client.get(f"/api/analysis/{analyzed_session_id}")
        assert resp.json()["session_id"] == analyzed_session_id

    def test_404_when_no_analysis_yet(self, client):
        """A fresh session with no analysis should return 404."""
        create_resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "Bug not yet analysed here"},
        )
        new_sid = create_resp.json()["id"]
        resp = client.get(f"/api/analysis/{new_sid}")
        assert resp.status_code == 404

    def test_404_for_unknown_session_id(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/analysis/{fake_id}")
        assert resp.status_code == 404

    def test_data_matches_post_result(self, client, session_id):
        """GET should return the same data as the POST that created it."""
        post_resp = client.post("/api/analysis", json={"session_id": session_id})
        get_resp = client.get(f"/api/analysis/{session_id}")
        assert post_resp.json()["relevant_files"] == get_resp.json()["relevant_files"]
        assert post_resp.json()["root_causes"] == get_resp.json()["root_causes"]


# ===========================================================================
# Analysis service unit tests
# ===========================================================================


class TestAnalysisServiceUnit:
    """Unit tests for analysis_service.analyze() using a mock LLM."""

    def _mock_llm(self, response_dict: dict | None = None):
        """Return a MagicMock that mimics LLMProvider.complete()."""
        mock = MagicMock()
        if response_dict is None:
            response_dict = {
                "relevant_files": [
                    {"path": "order_service.py", "confidence": 0.94, "reason": "Discount logic"}
                ],
                "root_causes": [
                    {"description": "Discount before tax", "file": "order_service.py", "line_hint": 27}
                ],
            }
        mock.complete.return_value = json.dumps(response_dict)
        return mock

    def test_analyze_returns_dict_with_session_id(self):
        from services.analysis_service import analyze

        llm = self._mock_llm()
        result = analyze("test-session", "discount bug", "order_service", llm)
        assert result["session_id"] == "test-session"

    def test_analyze_returns_relevant_files(self):
        from services.analysis_service import analyze

        llm = self._mock_llm()
        result = analyze("test-session", "discount bug", "order_service", llm)
        assert isinstance(result["relevant_files"], list)
        assert len(result["relevant_files"]) == 1

    def test_analyze_returns_root_causes(self):
        from services.analysis_service import analyze

        llm = self._mock_llm()
        result = analyze("test-session", "discount bug", "order_service", llm)
        assert isinstance(result["root_causes"], list)
        assert len(result["root_causes"]) == 1

    def test_analyze_uses_json_mode(self):
        from services.analysis_service import analyze

        llm = self._mock_llm()
        analyze("test-session", "discount bug", "order_service", llm)
        call_kwargs = llm.complete.call_args
        # json_mode=True must be passed
        assert call_kwargs.kwargs.get("json_mode") is True or (
            len(call_kwargs.args) >= 2 and call_kwargs.args[1] is True
        )

    def test_analyze_passes_messages_list(self):
        from services.analysis_service import analyze

        llm = self._mock_llm()
        analyze("test-session", "discount bug", "order_service", llm)
        messages = llm.complete.call_args.args[0]
        assert isinstance(messages, list)
        assert len(messages) >= 2  # system + user

    def test_analyze_raises_runtime_error_on_llm_failure(self):
        from services.analysis_service import analyze

        llm = MagicMock()
        llm.complete.side_effect = Exception("LLM unavailable")
        with pytest.raises(RuntimeError, match="LLM analysis failed"):
            analyze("test-session", "discount bug", "order_service", llm)

    def test_analyze_raises_value_error_on_bad_json(self):
        from services.analysis_service import analyze

        llm = MagicMock()
        llm.complete.return_value = "this is not json {"
        with pytest.raises(ValueError, match="invalid JSON"):
            analyze("test-session", "discount bug", "order_service", llm)

    def test_analyze_unknown_project_raises_value_error(self):
        from services.analysis_service import analyze

        llm = self._mock_llm()
        with pytest.raises(ValueError, match="not found"):
            analyze("test-session", "discount bug", "nonexistent_project_xyz", llm)

    def test_analyze_normalises_missing_confidence(self):
        from services.analysis_service import analyze

        llm = self._mock_llm(
            {
                "relevant_files": [{"path": "f.py", "reason": "some reason"}],  # no confidence
                "root_causes": [],
            }
        )
        result = analyze("s", "bug", "order_service", llm)
        # Should default to 0.5
        assert result["relevant_files"][0]["confidence"] == 0.5

    def test_analyze_normalises_missing_root_cause_file(self):
        from services.analysis_service import analyze

        llm = self._mock_llm(
            {
                "relevant_files": [],
                "root_causes": [{"description": "some bug"}],  # no file or line_hint
            }
        )
        result = analyze("s", "bug", "order_service", llm)
        assert result["root_causes"][0]["file"] == ""
        assert result["root_causes"][0]["line_hint"] is None

    def test_load_sample_project_files_order_service(self):
        from services.analysis_service import _load_sample_project_files

        contents = _load_sample_project_files("order_service")
        assert "order_service.py" in contents
        assert len(contents["order_service.py"]) > 0

    def test_load_sample_project_files_raises_for_unknown(self):
        from services.analysis_service import _load_sample_project_files

        with pytest.raises(ValueError, match="not found"):
            _load_sample_project_files("project_that_does_not_exist")

    def test_truncate_files_respects_limit(self):
        from services.analysis_service import _truncate_files, _MAX_FILE_CHARS

        big_content = "x" * 10000
        truncated = _truncate_files({"big_file.py": big_content})
        assert len(truncated["big_file.py"]) <= _MAX_FILE_CHARS

    def test_build_messages_includes_bug_description(self):
        from services.analysis_service import _build_messages

        msgs = _build_messages("my unique bug string", {"f.py": "x = 1"})
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "my unique bug string" in user_msg["content"]

    def test_build_messages_includes_file_content(self):
        from services.analysis_service import _build_messages

        msgs = _build_messages("a bug", {"f.py": "def foo(): pass"})
        user_msg = next(m for m in msgs if m["role"] == "user")
        assert "def foo(): pass" in user_msg["content"]

    def test_build_messages_has_system_prompt(self):
        from services.analysis_service import _build_messages

        msgs = _build_messages("a bug", {"f.py": "x = 1"})
        system_msg = next(m for m in msgs if m["role"] == "system")
        assert "JSON" in system_msg["content"]


# ===========================================================================
# Full end-to-end workflow test
# ===========================================================================


class TestEndToEndWorkflow:
    def test_full_flow_sample_project(self, client):
        """
        Full ST-5 workflow: create session → run analysis → retrieve result.
        """
        # 1. Create session
        sess_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "order_service",
                "bug_description": "Discount is applied before tax causing overcharge",
            },
        )
        assert sess_resp.status_code == 201
        session = sess_resp.json()
        assert session["status"] == "created"

        # 2. Run analysis
        analysis_resp = client.post("/api/analysis", json={"session_id": session["id"]})
        assert analysis_resp.status_code == 200
        result = analysis_resp.json()
        assert result["session_id"] == session["id"]
        assert isinstance(result["relevant_files"], list)
        assert isinstance(result["root_causes"], list)

        # 3. Session status updated
        session_after = client.get(f"/api/sessions/{session['id']}").json()
        assert session_after["status"] == "analyzed"

        # 4. Retrieve persisted analysis
        get_resp = client.get(f"/api/analysis/{session['id']}")
        assert get_resp.status_code == 200
        assert get_resp.json()["session_id"] == session["id"]

    def test_auth_service_analysis(self, client):
        """Analysis also works for the auth_service sample project."""
        sess_resp = client.post(
            "/api/sessions",
            json={
                "project_id": "auth_service",
                "bug_description": "JWT token is not expiring correctly",
            },
        )
        assert sess_resp.status_code == 201
        sid = sess_resp.json()["id"]

        analysis_resp = client.post("/api/analysis", json={"session_id": sid})
        assert analysis_resp.status_code == 200
        assert analysis_resp.json()["session_id"] == sid


# ===========================================================================
# ST-1 through ST-4 Regression tests
# ===========================================================================


class TestRegressionST1:
    def test_health_endpoint_still_works(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
        assert resp.json()["service"] == "devproof-ai"


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


class TestRegressionST4:
    def test_session_models_importable(self):
        from models.session import Session, SessionCreate, SessionStatus
        assert SessionStatus.analyzed == "analyzed"

    def test_analysis_models_importable(self):
        from models.analysis import AnalysisResult, FileRelevance, RootCause
        ar = AnalysisResult(
            session_id="s",
            relevant_files=[FileRelevance(path="f.py", confidence=0.8, reason="r")],
            root_causes=[RootCause(description="d", file="f.py")],
        )
        assert ar.session_id == "s"

    def test_db_tables_exist(self):
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
            assert "sessions" in tables
            assert "analyses" in tables
