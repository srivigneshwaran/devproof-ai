"""
Tests for ST-8: Error Handling & Startup Validation (Backend).

Covers every ST-8 requirement:

1. Global exception handler — unhandled Exception → HTTP 500
   { "error": "Internal Server Error", "detail": "..." }

2. HTTPException handler — all HTTPExceptions normalised to
   { "error": "<label>", "detail": "<message>" }
   (verified for 404, 409, 422, 503)

3. LLMServiceError — defined and exported from llm.exceptions;
   service-layer LLM failures raise LLMServiceError;
   router layer maps LLMServiceError → HTTP 503.

4. Startup env-var validation — validate_env() raises RuntimeError
   with a clear message when required vars are missing.

5. Subprocess timeout → verdict "ERROR",
   test_output contains "timed out after 30s".
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Force mock LLM for this entire module.
os.environ["LLM_PROVIDER"] = "mock"

_BACKEND_DIR = Path(__file__).resolve().parent.parent


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture(scope="module")
def client():
    """Shared FastAPI TestClient for the full application."""
    from fastapi.testclient import TestClient
    import main as app_module

    with TestClient(app_module.app) as c:
        yield c


def _create_session(client, project_id="order_service", bug_desc="Test bug") -> str:
    resp = client.post(
        "/api/sessions",
        json={"project_id": project_id, "bug_description": bug_desc},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def _seed_analysis(session_id: str) -> None:
    from db.database import get_connection

    analysis_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO analyses (id, session_id, relevant_files, root_causes, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                session_id,
                json.dumps(
                    [{"path": "order_service.py", "confidence": 0.9, "reason": "x"}]
                ),
                json.dumps(
                    [{"description": "bug", "file": "order_service.py", "line_hint": 1}]
                ),
                now,
            ),
        )
        conn.execute(
            "UPDATE sessions SET status = 'analyzed' WHERE id = ?", (session_id,)
        )


def _seed_fix(session_id: str) -> None:
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
                "discount_amount = subtotal * discount_rate          # BUG: should use subtotal * tax_rate",
                "discount_amount = subtotal * tax_rate * discount_rate",
                "Tax before discount.",
                now,
            ),
        )
        conn.execute(
            "UPDATE sessions SET status = 'fix_proposed' WHERE id = ?", (session_id,)
        )


def _seed_approval(session_id: str) -> None:
    from db.database import get_connection

    approval_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO fix_approvals (id, session_id, approved, feedback, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (approval_id, session_id, 1, None, now),
        )
        conn.execute(
            "UPDATE sessions SET status = 'fix_approved' WHERE id = ?", (session_id,)
        )


# ===========================================================================
# 1. LLMServiceError — definition and properties
# ===========================================================================


class TestLLMServiceError:
    """LLMServiceError must be importable, subclass Exception, carry message."""

    def test_importable_from_llm_exceptions(self):
        from llm.exceptions import LLMServiceError

        assert LLMServiceError is not None

    def test_is_exception_subclass(self):
        from llm.exceptions import LLMServiceError

        assert issubclass(LLMServiceError, Exception)

    def test_message_stored_on_instance(self):
        from llm.exceptions import LLMServiceError

        err = LLMServiceError("provider down")
        assert err.message == "provider down"

    def test_original_exception_stored(self):
        from llm.exceptions import LLMServiceError

        original = ValueError("root cause")
        err = LLMServiceError("wrapped", original)
        assert err.original is original

    def test_str_includes_message(self):
        from llm.exceptions import LLMServiceError

        err = LLMServiceError("provider down")
        assert "provider down" in str(err)

    def test_str_includes_original_when_set(self):
        from llm.exceptions import LLMServiceError

        err = LLMServiceError("wrapped", ValueError("root"))
        assert "root" in str(err)

    def test_no_original_is_none(self):
        from llm.exceptions import LLMServiceError

        err = LLMServiceError("only message")
        assert err.original is None

    def test_can_be_raised_and_caught(self):
        from llm.exceptions import LLMServiceError

        with pytest.raises(LLMServiceError, match="test error"):
            raise LLMServiceError("test error")


# ===========================================================================
# 2. Service layer raises LLMServiceError on LLM failure
# ===========================================================================


class TestServiceLayerRaisesLLMServiceError:
    """All service LLM calls must raise LLMServiceError, not RuntimeError/ValueError."""

    def test_analysis_service_raises_on_llm_failure(self):
        from llm.exceptions import LLMServiceError
        from services.analysis_service import analyze

        llm = MagicMock()
        llm.complete.side_effect = Exception("provider down")
        with pytest.raises(LLMServiceError):
            analyze("s1", "bug", "order_service", llm)

    def test_analysis_service_raises_on_bad_json(self):
        from llm.exceptions import LLMServiceError
        from services.analysis_service import analyze

        llm = MagicMock()
        llm.complete.return_value = "not json {"
        with pytest.raises(LLMServiceError, match="invalid JSON"):
            analyze("s1", "bug", "order_service", llm)

    def test_fix_service_raises_on_llm_failure(self):
        from llm.exceptions import LLMServiceError
        from services.fix_service import generate_fixes

        llm = MagicMock()
        llm.complete.side_effect = Exception("provider down")
        analysis = {
            "relevant_files": [
                {"path": "order_service.py", "confidence": 0.9, "reason": "x"}
            ],
            "root_causes": [],
        }
        with pytest.raises(LLMServiceError):
            generate_fixes("s1", "bug", "order_service", analysis, llm)

    def test_fix_service_raises_on_bad_json(self):
        from llm.exceptions import LLMServiceError
        from services.fix_service import generate_fixes

        llm = MagicMock()
        llm.complete.return_value = "not valid json {"
        analysis = {
            "relevant_files": [
                {"path": "order_service.py", "confidence": 0.9, "reason": "x"}
            ],
            "root_causes": [],
        }
        with pytest.raises(LLMServiceError, match="invalid JSON"):
            generate_fixes("s1", "bug", "order_service", analysis, llm)

    def test_test_service_raises_on_llm_failure(self):
        from llm.exceptions import LLMServiceError
        from services.test_service import generate_tests

        llm = MagicMock()
        llm.complete.side_effect = Exception("provider down")
        fix = {
            "id": "f1",
            "session_id": "s1",
            "file_path": "order_service.py",
            "original": "x",
            "suggested": "y",
            "explanation": "z",
        }
        with pytest.raises(LLMServiceError):
            generate_tests("s1", [fix], "bug", llm)


# ===========================================================================
# 3. Router layer maps LLMServiceError → HTTP 503
# ===========================================================================


class TestRouterMapsLLMServiceErrorTo503:
    """All three routers must return 503 when the LLM call fails."""

    def test_analysis_router_503_on_llm_failure(self, client):
        import main as app_module

        sid = _create_session(client)
        original_llm = app_module.app.state.llm
        failing_llm = MagicMock()
        failing_llm.complete.side_effect = Exception("LLM outage")
        app_module.app.state.llm = failing_llm
        try:
            resp = client.post("/api/analysis", json={"session_id": sid})
            assert resp.status_code == 503
        finally:
            app_module.app.state.llm = original_llm

    def test_fix_router_503_on_llm_failure(self, client):
        import main as app_module

        sid = _create_session(client)
        _seed_analysis(sid)

        original_llm = app_module.app.state.llm
        failing_llm = MagicMock()
        failing_llm.complete.side_effect = Exception("LLM outage")
        app_module.app.state.llm = failing_llm
        try:
            resp = client.post("/api/fix", json={"session_id": sid})
            assert resp.status_code == 503
        finally:
            app_module.app.state.llm = original_llm

    def test_verify_router_503_on_llm_failure(self, client):
        import main as app_module

        sid = _create_session(client)
        _seed_analysis(sid)
        _seed_fix(sid)
        _seed_approval(sid)

        original_llm = app_module.app.state.llm
        failing_llm = MagicMock()
        failing_llm.complete.side_effect = Exception("LLM outage")
        app_module.app.state.llm = failing_llm
        try:
            resp = client.post("/api/verify", json={"session_id": sid})
            assert resp.status_code == 503
        finally:
            app_module.app.state.llm = original_llm


# ===========================================================================
# 4. Error response envelope shape
# ===========================================================================


class TestErrorEnvelope:
    """All error responses must have {"error": ..., "detail": ...} shape."""

    def test_404_has_error_and_detail_keys(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/sessions/{fake_id}")
        assert resp.status_code == 404
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_404_error_field_is_not_found(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/sessions/{fake_id}")
        assert resp.json()["error"] == "Not Found"

    def test_409_has_error_and_detail_keys(self, client):
        """Verify POST → 409 (no approval) has standard envelope."""
        sid = _create_session(client)
        resp = client.post("/api/verify", json={"session_id": sid})
        assert resp.status_code == 409
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_409_error_field_is_conflict(self, client):
        sid = _create_session(client)
        resp = client.post("/api/verify", json={"session_id": sid})
        assert resp.json()["error"] == "Conflict"

    def test_422_has_error_and_detail_keys(self, client):
        """Missing required field in request body → 422."""
        resp = client.post("/api/sessions", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_422_error_field_is_unprocessable(self, client):
        resp = client.post("/api/sessions", json={})
        assert resp.json()["error"] == "Unprocessable Entity"

    def test_503_has_error_and_detail_keys(self, client):
        """LLM failure → 503 with standard envelope."""
        import main as app_module

        sid = _create_session(client)
        original_llm = app_module.app.state.llm
        failing_llm = MagicMock()
        failing_llm.complete.side_effect = Exception("outage")
        app_module.app.state.llm = failing_llm
        try:
            resp = client.post("/api/analysis", json={"session_id": sid})
            assert resp.status_code == 503
            body = resp.json()
            assert "error" in body
            assert "detail" in body
        finally:
            app_module.app.state.llm = original_llm

    def test_503_error_field_is_service_unavailable(self, client):
        import main as app_module

        sid = _create_session(client)
        original_llm = app_module.app.state.llm
        failing_llm = MagicMock()
        failing_llm.complete.side_effect = Exception("outage")
        app_module.app.state.llm = failing_llm
        try:
            resp = client.post("/api/analysis", json={"session_id": sid})
            assert resp.json()["error"] == "Service Unavailable"
        finally:
            app_module.app.state.llm = original_llm

    def test_500_unhandled_exception_returns_error_envelope(self):
        """An unhandled exception on a route must return 500 with error envelope."""
        import main as app_module
        from fastapi import APIRouter
        from fastapi.testclient import TestClient

        # Use a fresh client with raise_server_exceptions=False so that the
        # global exception handler can intercept the RuntimeError and return 500.
        _router = APIRouter()

        @_router.get("/test-st8-boom")
        def boom():
            raise RuntimeError("unexpected internal error")

        app_module.app.include_router(_router)
        try:
            with TestClient(app_module.app, raise_server_exceptions=False) as tc:
                resp = tc.get("/test-st8-boom")
            assert resp.status_code == 500
            body = resp.json()
            assert "error" in body
            assert "detail" in body
            assert body["error"] == "Internal Server Error"
        finally:
            app_module.app.routes[:] = [
                r for r in app_module.app.routes
                if getattr(r, "path", None) != "/test-st8-boom"
            ]


# ===========================================================================
# 5. Startup env-var validation — validate_env()
# ===========================================================================


class TestStartupValidation:
    """validate_env() must raise RuntimeError when required vars are missing."""

    def test_mock_provider_requires_no_vars(self):
        """mock provider must pass validation with no env vars set."""
        from llm.factory import validate_env

        with patch.dict(os.environ, {"LLM_PROVIDER": "mock"}, clear=False):
            # Must not raise
            validate_env()

    def test_watsonx_missing_all_keys_raises(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "watsonx",
            "WATSONX_API_KEY": "",
            "WATSONX_PROJECT_ID": "",
            "WATSONX_URL": "",
            "LLM_MODEL": "",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with pytest.raises(RuntimeError, match="WATSONX_API_KEY"):
                validate_env()

    def test_watsonx_missing_api_key_raises(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "watsonx",
            "WATSONX_API_KEY": "",
            "WATSONX_PROJECT_ID": "proj-123",
            "WATSONX_URL": "https://example.com",
            "LLM_MODEL": "ibm/granite",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with pytest.raises(RuntimeError, match="WATSONX_API_KEY"):
                validate_env()

    def test_watsonx_missing_model_raises(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "watsonx",
            "WATSONX_API_KEY": "key",
            "WATSONX_PROJECT_ID": "proj",
            "WATSONX_URL": "https://example.com",
            "LLM_MODEL": "",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with pytest.raises(RuntimeError, match="LLM_MODEL"):
                validate_env()

    def test_watsonx_all_vars_set_passes(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "watsonx",
            "WATSONX_API_KEY": "key",
            "WATSONX_PROJECT_ID": "proj",
            "WATSONX_URL": "https://example.com",
            "LLM_MODEL": "ibm/granite",
        }
        with patch.dict(os.environ, env_override, clear=False):
            # Must not raise
            validate_env()

    def test_openai_missing_api_key_raises(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "",
            "LLM_MODEL": "gpt-4o",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                validate_env()

    def test_openai_missing_model_raises(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-key",
            "LLM_MODEL": "",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with pytest.raises(RuntimeError, match="LLM_MODEL"):
                validate_env()

    def test_openai_all_vars_set_passes(self):
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "sk-key",
            "LLM_MODEL": "gpt-4o",
        }
        with patch.dict(os.environ, env_override, clear=False):
            # Must not raise
            validate_env()

    def test_error_message_mentions_provider_name(self):
        """The RuntimeError message must name the provider that failed validation."""
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "",
            "LLM_MODEL": "",
        }
        with patch.dict(os.environ, env_override, clear=False):
            with pytest.raises(RuntimeError, match="openai"):
                validate_env()

    def test_error_message_names_all_missing_vars(self):
        """The RuntimeError message must list every missing variable."""
        from llm.factory import validate_env

        env_override = {
            "LLM_PROVIDER": "openai",
            "OPENAI_API_KEY": "",
            "LLM_MODEL": "",
        }
        with patch.dict(os.environ, env_override, clear=False):
            try:
                validate_env()
                pytest.fail("Expected RuntimeError was not raised")
            except RuntimeError as exc:
                msg = str(exc)
                assert "OPENAI_API_KEY" in msg
                assert "LLM_MODEL" in msg


# ===========================================================================
# 6. Subprocess timeout → verdict ERROR with correct message
# ===========================================================================


class TestSubprocessTimeout:
    """Subprocess timeout must yield verdict=ERROR and the expected message."""

    def test_timeout_verdict_is_error(self):
        from services.report_service import _compute_verdict

        verdict = _compute_verdict(0, 0, 0, timed_out=True, exit_code=-1)
        assert verdict == "ERROR"

    def test_timeout_test_output_message(self):
        """validation_service must set test_output to the expected timeout string."""
        import subprocess
        from services.validation_service import run_tests, _WORKSPACE_ROOT
        import shutil

        sid = "st8-timeout-" + str(uuid.uuid4())[:8]
        ws = _WORKSPACE_ROOT / sid
        ws.mkdir(parents=True, exist_ok=True)

        tests = [{"file": "test_t.py", "code": "import time\ntime.sleep(99)\ndef test_x(): pass\n"}]
        try:
            with patch(
                "services.validation_service.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=30),
            ):
                result = run_tests(
                    session_id=sid,
                    generated_tests=tests,
                    fixes=[],
                    project_id="order_service",
                )
            assert result["timed_out"] is True
            assert "timed out after 30s" in result["test_output"]
        finally:
            if ws.exists():
                shutil.rmtree(str(ws), ignore_errors=True)

    def test_timeout_timed_out_flag_true(self):
        """validation_service result must have timed_out=True on timeout."""
        import subprocess
        from services.validation_service import run_tests, _WORKSPACE_ROOT
        import shutil

        sid = "st8-timeout2-" + str(uuid.uuid4())[:8]
        ws = _WORKSPACE_ROOT / sid
        ws.mkdir(parents=True, exist_ok=True)

        tests = [{"file": "test_t2.py", "code": "def test_x(): pass\n"}]
        try:
            with patch(
                "services.validation_service.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd=["pytest"], timeout=30),
            ):
                result = run_tests(sid, tests, [], "order_service")
            assert result["timed_out"] is True
        finally:
            if ws.exists():
                shutil.rmtree(str(ws), ignore_errors=True)
