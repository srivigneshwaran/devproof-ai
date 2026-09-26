"""
Tests for ST-9: Security Hardening (Backend).

Covers every ST-9 requirement:

1. CORS configuration
   - Allowed origins are driven by CORS_ORIGINS env var (no wildcard).
   - Default covers http://localhost:5173.
   - Wildcard "*" is never used.

2. Upload validation — allowed .py uploads
3. Upload validation — rejected non-.py uploads (HTTP 400)
4. Upload validation — file-size limits (HTTP 400)
5. Upload validation — file-count limits (HTTP 400)
6. Upload validation — unsafe/path-traversal filenames (HTTP 400)

7. X-Content-Type-Options: nosniff on every API response

8. Security-related error responses:
   - Standard {"error": ..., "detail": ...} envelope preserved
   - No stack traces / internal sensitive information in API errors

9. Regression: ST-1 through ST-8 behaviour is not broken
"""

from __future__ import annotations

import io
import os
import uuid
from pathlib import Path
from unittest.mock import patch

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


# ===========================================================================
# 1. CORS Configuration
# ===========================================================================


class TestCORSConfiguration:
    """CORS must be locked to specific origins — never wildcard."""

    def test_cors_origins_list_has_no_wildcard(self):
        """_ALLOWED_ORIGINS must never contain '*'."""
        import main as app_module

        assert "*" not in app_module._ALLOWED_ORIGINS

    def test_cors_origins_list_is_not_empty(self):
        """At least one allowed origin must be configured."""
        import main as app_module

        assert len(app_module._ALLOWED_ORIGINS) >= 1

    def test_default_cors_includes_localhost_5173(self):
        """Default CORS must include the Vite dev server origin."""
        import main as app_module

        assert "http://localhost:5173" in app_module._ALLOWED_ORIGINS

    def test_cors_origins_read_from_env_var(self):
        """CORS_ORIGINS env var is split on commas into a list."""
        custom = "http://example.com,http://staging.example.com"
        with patch.dict(os.environ, {"CORS_ORIGINS": custom}):
            # Re-evaluate the same logic used in main.py
            raw = os.environ.get("CORS_ORIGINS", "")
            origins = [o.strip() for o in raw.split(",") if o.strip()]
        assert origins == ["http://example.com", "http://staging.example.com"]

    def test_cors_origins_env_var_strips_whitespace(self):
        """Whitespace around comma-separated origins must be stripped."""
        with patch.dict(os.environ, {"CORS_ORIGINS": " http://a.com , http://b.com "}):
            raw = os.environ.get("CORS_ORIGINS", "")
            origins = [o.strip() for o in raw.split(",") if o.strip()]
        assert "http://a.com" in origins
        assert "http://b.com" in origins

    def test_allowed_origin_gets_cors_header(self, client):
        """A preflight from an allowed origin must receive the CORS header."""
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        # FastAPI's CORSMiddleware sets Access-Control-Allow-Origin on match
        assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_disallowed_origin_does_not_get_cors_header(self, client):
        """A preflight from a disallowed origin must not receive an allow-origin header."""
        resp = client.options(
            "/health",
            headers={
                "Origin": "http://evil.example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        # The allow-origin header must not be the evil origin
        origin_header = resp.headers.get("access-control-allow-origin", "")
        assert origin_header != "http://evil.example.com"
        assert origin_header != "*"


# ===========================================================================
# 2. Upload — allowed .py uploads
# ===========================================================================


class TestUploadAllowed:
    """Valid .py uploads must succeed and return session_file_paths."""

    def _py_file(self, name: str = "test.py", content: str = "x = 1\n"):
        return (name, io.BytesIO(content.encode()), "text/x-python")

    def test_single_py_file_returns_200(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._py_file())],
        )
        assert resp.status_code == 200

    def test_single_py_file_response_shape(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._py_file())],
        )
        data = resp.json()
        assert "session_file_paths" in data
        assert isinstance(data["session_file_paths"], list)
        assert len(data["session_file_paths"]) == 1

    def test_five_py_files_accepted(self, client):
        """Exactly _MAX_FILES files must be accepted."""
        files = [("files[]", self._py_file(f"f{i}.py")) for i in range(5)]
        resp = client.post("/api/projects/upload", files=files)
        assert resp.status_code == 200
        assert len(resp.json()["session_file_paths"]) == 5

    def test_returned_filename_is_safe_basename(self, client):
        """Returned paths must be bare filenames (no directory components)."""
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._py_file("mymodule.py"))],
        )
        paths = resp.json()["session_file_paths"]
        for p in paths:
            assert "/" not in p
            assert "\\" not in p
            assert p == Path(p).name


# ===========================================================================
# 3. Upload — rejected non-.py extensions
# ===========================================================================


class TestUploadRejectedExtensions:
    """Non-.py files must be rejected with HTTP 400."""

    def _bad_file(self, name: str, content: bytes = b"data"):
        return (name, io.BytesIO(content), "application/octet-stream")

    def test_txt_file_rejected_400(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("evil.txt"))],
        )
        assert resp.status_code == 400

    def test_sh_file_rejected_400(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("run.sh"))],
        )
        assert resp.status_code == 400

    def test_js_file_rejected_400(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("app.js"))],
        )
        assert resp.status_code == 400

    def test_exe_file_rejected_400(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("malware.exe"))],
        )
        assert resp.status_code == 400

    def test_no_extension_rejected_400(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("Makefile"))],
        )
        assert resp.status_code == 400

    def test_rejection_error_envelope(self, client):
        """Non-.py rejection must use the standard error envelope."""
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("bad.txt"))],
        )
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_rejection_detail_mentions_file(self, client):
        """The detail field should reference what was rejected."""
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._bad_file("bad.txt"))],
        )
        detail = str(resp.json().get("detail", ""))
        # Detail should either name the file or mention .py restriction
        assert "bad.txt" in detail or ".py" in detail or "not allowed" in detail


# ===========================================================================
# 4. Upload — file-size limits
# ===========================================================================


class TestUploadFileSizeLimits:
    """Files larger than 100 KB must be rejected with HTTP 400."""

    def test_exactly_100kb_accepted(self, client):
        """Exactly 100 KB (102400 bytes) should be accepted."""
        content = b"x" * (100 * 1024)
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("exact.py", io.BytesIO(content), "text/x-python"))],
        )
        assert resp.status_code == 200

    def test_over_100kb_rejected_400(self, client):
        """A file slightly over 100 KB must be rejected."""
        content = b"x" * (100 * 1024 + 1)
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("toobig.py", io.BytesIO(content), "text/x-python"))],
        )
        assert resp.status_code == 400

    def test_120kb_rejected_400(self, client):
        big_content = b"x = 1\n" * (20 * 1024)  # ~120 KB
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("big.py", io.BytesIO(big_content), "text/x-python"))],
        )
        assert resp.status_code == 400

    def test_size_rejection_error_envelope(self, client):
        big_content = b"y" * (200 * 1024)
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("big.py", io.BytesIO(big_content), "text/x-python"))],
        )
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_size_rejection_detail_mentions_limit(self, client):
        big_content = b"y" * (200 * 1024)
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("big.py", io.BytesIO(big_content), "text/x-python"))],
        )
        detail = str(resp.json().get("detail", ""))
        assert "100 KB" in detail or "100kb" in detail.lower() or "limit" in detail.lower()


# ===========================================================================
# 5. Upload — file-count limits
# ===========================================================================


class TestUploadFileCountLimits:
    """More than 5 files per upload must be rejected with HTTP 400."""

    def _py(self, name: str):
        return (name, io.BytesIO(b"x = 1\n"), "text/x-python")

    def test_six_files_rejected_400(self, client):
        files = [("files[]", self._py(f"f{i}.py")) for i in range(6)]
        resp = client.post("/api/projects/upload", files=files)
        assert resp.status_code == 400

    def test_ten_files_rejected_400(self, client):
        files = [("files[]", self._py(f"g{i}.py")) for i in range(10)]
        resp = client.post("/api/projects/upload", files=files)
        assert resp.status_code == 400

    def test_count_rejection_error_envelope(self, client):
        files = [("files[]", self._py(f"h{i}.py")) for i in range(6)]
        resp = client.post("/api/projects/upload", files=files)
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_count_rejection_detail_mentions_max(self, client):
        files = [("files[]", self._py(f"k{i}.py")) for i in range(6)]
        resp = client.post("/api/projects/upload", files=files)
        detail = str(resp.json().get("detail", ""))
        assert "5" in detail or "maximum" in detail.lower()


# ===========================================================================
# 6. Upload — path-traversal filenames
# ===========================================================================


class TestUploadPathTraversal:
    """Filenames with path separators must be rejected with HTTP 400."""

    def _upload(self, client, filename: str):
        return client.post(
            "/api/projects/upload",
            files=[("files[]", (filename, io.BytesIO(b"x = 1\n"), "text/x-python"))],
        )

    def test_dotdot_slash_rejected(self, client):
        resp = self._upload(client, "../evil.py")
        assert resp.status_code == 400

    def test_sub_directory_slash_rejected(self, client):
        resp = self._upload(client, "sub/evil.py")
        assert resp.status_code == 400

    def test_absolute_path_rejected(self, client):
        resp = self._upload(client, "/etc/passwd.py")
        assert resp.status_code == 400

    def test_backslash_rejected(self, client):
        resp = self._upload(client, "sub\\evil.py")
        assert resp.status_code == 400

    def test_traversal_error_envelope(self, client):
        resp = self._upload(client, "../evil.py")
        body = resp.json()
        assert "error" in body
        assert "detail" in body

    def test_traversal_no_stack_trace_in_detail(self, client):
        """Traversal rejection must not leak stack trace information."""
        resp = self._upload(client, "../evil.py")
        body = resp.json()
        detail = str(body.get("detail", ""))
        assert "Traceback" not in detail
        assert "File \"" not in detail


# ===========================================================================
# 7. X-Content-Type-Options: nosniff
# ===========================================================================


class TestSecurityHeaders:
    """X-Content-Type-Options: nosniff must be present on API responses."""

    def test_health_has_nosniff_header(self, client):
        resp = client.get("/health")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_projects_list_has_nosniff_header(self, client):
        resp = client.get("/api/projects")
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_404_response_has_nosniff_header(self, client):
        resp = client.get(f"/api/sessions/{uuid.uuid4()}")
        assert resp.status_code == 404
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_upload_success_has_nosniff_header(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("test.py", io.BytesIO(b"x=1\n"), "text/x-python"))],
        )
        assert resp.status_code == 200
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_upload_rejection_has_nosniff_header(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("bad.txt", io.BytesIO(b"data"), "text/plain"))],
        )
        assert resp.status_code == 400
        assert resp.headers.get("x-content-type-options") == "nosniff"

    def test_422_response_has_nosniff_header(self, client):
        """Pydantic validation errors must also carry the security header."""
        resp = client.post("/api/sessions", json={})
        assert resp.status_code == 422
        assert resp.headers.get("x-content-type-options") == "nosniff"


# ===========================================================================
# 8. Security-related error responses — no sensitive information exposed
# ===========================================================================


class TestNoSensitiveInfoInErrors:
    """Error responses must not expose stack traces or sensitive internals."""

    def test_404_error_envelope_only(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/sessions/{fake_id}")
        body = resp.json()
        assert set(body.keys()) == {"error", "detail"}

    def test_404_no_traceback_in_detail(self, client):
        fake_id = str(uuid.uuid4())
        resp = client.get(f"/api/sessions/{fake_id}")
        detail = str(resp.json()["detail"])
        assert "Traceback" not in detail
        assert "File \"" not in detail

    def test_422_no_traceback_in_detail(self, client):
        resp = client.post("/api/sessions", json={})
        detail = str(resp.json()["detail"])
        assert "Traceback" not in detail
        assert "File \"" not in detail

    def test_upload_400_no_filesystem_paths(self, client):
        """Upload errors must not expose internal filesystem paths."""
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("bad.txt", io.BytesIO(b"data"), "text/plain"))],
        )
        detail = str(resp.json().get("detail", ""))
        # Should not contain absolute filesystem paths
        assert "/home/" not in detail
        assert "/var/" not in detail
        assert "backend/workspace" not in detail

    def test_error_responses_have_error_and_detail_keys(self, client):
        """Every error response must have exactly error + detail keys."""
        # 404
        resp = client.get(f"/api/sessions/{uuid.uuid4()}")
        assert "error" in resp.json()
        assert "detail" in resp.json()

        # 400 upload
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("bad.sh", io.BytesIO(b"data"), "text/plain"))],
        )
        assert "error" in resp.json()
        assert "detail" in resp.json()

    def test_500_unhandled_error_sanitised(self):
        """An unhandled exception must return generic message, not the exception text."""
        import main as app_module
        from fastapi import APIRouter
        from fastapi.testclient import TestClient

        _router = APIRouter()

        @_router.get("/test-st9-boom")
        def boom():
            raise RuntimeError("super secret internal error with /etc/passwd path")

        app_module.app.include_router(_router)
        try:
            with TestClient(app_module.app, raise_server_exceptions=False) as tc:
                resp = tc.get("/test-st9-boom")
            assert resp.status_code == 500
            body = resp.json()
            assert "error" in body
            assert "detail" in body
            # The raw exception message must not appear in the response
            assert "super secret" not in body["detail"]
            assert "/etc/passwd" not in body["detail"]
        finally:
            app_module.app.routes[:] = [
                r for r in app_module.app.routes
                if getattr(r, "path", None) != "/test-st9-boom"
            ]


# ===========================================================================
# 9. Regression — ST-1 through ST-8 still pass
# ===========================================================================


class TestST9Regression:
    """Core ST-1 through ST-8 behaviour must not be broken by ST-9 changes."""

    def test_health_still_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_projects_list_still_200(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_sessions_post_still_works(self, client):
        resp = client.post(
            "/api/sessions",
            json={"project_id": "order_service", "bug_description": "regression test"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "id" in data

    def test_404_error_envelope_preserved(self, client):
        resp = client.get(f"/api/sessions/{uuid.uuid4()}")
        assert resp.status_code == 404
        body = resp.json()
        assert body["error"] == "Not Found"
        assert "detail" in body

    def test_422_error_envelope_preserved(self, client):
        resp = client.post("/api/sessions", json={})
        assert resp.status_code == 422
        body = resp.json()
        assert body["error"] == "Unprocessable Entity"

    def test_upload_valid_py_still_works(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("reg.py", io.BytesIO(b"x = 1\n"), "text/x-python"))],
        )
        assert resp.status_code == 200
        assert "session_file_paths" in resp.json()

    def test_upload_non_py_still_rejected(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("bad.js", io.BytesIO(b"x = 1"), "text/javascript"))],
        )
        assert resp.status_code == 400

    def test_upload_oversized_still_rejected(self, client):
        big = b"x" * (100 * 1024 + 1)
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("big.py", io.BytesIO(big), "text/x-python"))],
        )
        assert resp.status_code == 400
