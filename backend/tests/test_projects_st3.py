"""
Tests for ST-3: Sample Projects & File Workspace.

Covers:
- project discovery (list_projects service)
- project metadata shape and values
- GET /api/projects endpoint
- GET /api/projects/{id}/files endpoint
- POST /api/projects/upload endpoint (constraints)
- expected response shapes matching the REST API contract
- ST-1 health endpoint still works
- ST-2 LLM provider tests are unaffected (validated by separate test file)
"""

import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module", autouse=True)
def set_mock_provider(monkeypatch_module=None):
    """Ensure LLM_PROVIDER=mock for all tests in this module."""
    os.environ.setdefault("LLM_PROVIDER", "mock")


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("LLM_PROVIDER", "mock")
    import main as app_module  # noqa: PLC0415

    with TestClient(app_module.app) as c:
        yield c


# ---------------------------------------------------------------------------
# Project Service unit tests
# ---------------------------------------------------------------------------

class TestProjectService:
    def test_list_projects_returns_list(self):
        from services.project_service import list_projects
        projects = list_projects()
        assert isinstance(projects, list)

    def test_list_projects_contains_order_service(self):
        from services.project_service import list_projects
        projects = list_projects()
        ids = [p["id"] for p in projects]
        assert "order_service" in ids

    def test_list_projects_contains_auth_service(self):
        from services.project_service import list_projects
        projects = list_projects()
        ids = [p["id"] for p in projects]
        assert "auth_service" in ids

    def test_list_projects_minimum_two(self):
        from services.project_service import list_projects
        projects = list_projects()
        assert len(projects) >= 2

    def test_project_metadata_shape(self):
        from services.project_service import list_projects
        for project in list_projects():
            assert "id" in project
            assert "name" in project
            assert "description" in project
            assert "file_count" in project
            assert isinstance(project["id"], str)
            assert isinstance(project["name"], str)
            assert isinstance(project["description"], str)
            assert isinstance(project["file_count"], int)

    def test_order_service_metadata(self):
        from services.project_service import list_projects
        projects = list_projects()
        order = next(p for p in projects if p["id"] == "order_service")
        assert order["name"] == "Order Service"
        assert "discount" in order["description"].lower() or "order" in order["description"].lower()
        assert order["file_count"] == 1

    def test_auth_service_metadata(self):
        from services.project_service import list_projects
        projects = list_projects()
        auth = next(p for p in projects if p["id"] == "auth_service")
        assert auth["name"] == "Auth Service"
        assert "token" in auth["description"].lower() or "auth" in auth["description"].lower()
        assert auth["file_count"] == 1

    def test_get_project_files_order_service(self):
        from services.project_service import get_project_files
        files = get_project_files("order_service")
        assert files is not None
        assert len(files) == 1
        assert files[0]["path"] == "order_service.py"
        assert isinstance(files[0]["description"], str)

    def test_get_project_files_auth_service(self):
        from services.project_service import get_project_files
        files = get_project_files("auth_service")
        assert files is not None
        assert len(files) == 1
        assert files[0]["path"] == "auth.py"

    def test_get_project_files_unknown_returns_none(self):
        from services.project_service import get_project_files
        result = get_project_files("does_not_exist")
        assert result is None

    def test_list_projects_is_deterministic(self):
        from services.project_service import list_projects
        r1 = list_projects()
        r2 = list_projects()
        assert r1 == r2


# ---------------------------------------------------------------------------
# GET /api/projects
# ---------------------------------------------------------------------------

class TestGetProjects:
    def test_status_200(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200

    def test_returns_list(self, client):
        resp = client.get("/api/projects")
        data = resp.json()
        assert isinstance(data, list)

    def test_contains_order_service(self, client):
        resp = client.get("/api/projects")
        ids = [p["id"] for p in resp.json()]
        assert "order_service" in ids

    def test_contains_auth_service(self, client):
        resp = client.get("/api/projects")
        ids = [p["id"] for p in resp.json()]
        assert "auth_service" in ids

    def test_response_shape(self, client):
        """Every item must have the exact fields from the REST API contract."""
        resp = client.get("/api/projects")
        for item in resp.json():
            assert set(item.keys()) == {"id", "name", "description", "file_count"}
            assert isinstance(item["id"], str)
            assert isinstance(item["name"], str)
            assert isinstance(item["description"], str)
            assert isinstance(item["file_count"], int)

    def test_order_service_values(self, client):
        resp = client.get("/api/projects")
        order = next(p for p in resp.json() if p["id"] == "order_service")
        assert order["name"] == "Order Service"
        assert order["file_count"] == 1

    def test_auth_service_values(self, client):
        resp = client.get("/api/projects")
        auth = next(p for p in resp.json() if p["id"] == "auth_service")
        assert auth["name"] == "Auth Service"
        assert auth["file_count"] == 1

    def test_content_type_is_json(self, client):
        resp = client.get("/api/projects")
        assert "application/json" in resp.headers["content-type"]


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/files
# ---------------------------------------------------------------------------

class TestGetProjectFiles:
    def test_order_service_files(self, client):
        resp = client.get("/api/projects/order_service/files")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["path"] == "order_service.py"

    def test_auth_service_files(self, client):
        resp = client.get("/api/projects/auth_service/files")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["path"] == "auth.py"

    def test_file_shape(self, client):
        resp = client.get("/api/projects/order_service/files")
        for f in resp.json():
            assert "path" in f
            assert "description" in f

    def test_unknown_project_returns_404(self, client):
        resp = client.get("/api/projects/nonexistent_project/files")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/projects/upload — constraint validation
# ---------------------------------------------------------------------------

class TestUploadFiles:
    def _make_py_file(self, name: str = "test.py", content: str = "x = 1\n"):
        return (name, io.BytesIO(content.encode()), "text/x-python")

    def test_upload_single_py_file(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._make_py_file())],
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "session_file_paths" in data
        assert isinstance(data["session_file_paths"], list)
        assert len(data["session_file_paths"]) == 1

    def test_upload_multiple_py_files(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[
                ("files[]", self._make_py_file("a.py")),
                ("files[]", self._make_py_file("b.py")),
            ],
        )
        assert resp.status_code == 200
        assert len(resp.json()["session_file_paths"]) == 2

    def test_upload_rejects_non_py(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("evil.txt", io.BytesIO(b"data"), "text/plain"))],
        )
        # ST-9: upload validation returns 400 for invalid files
        assert resp.status_code == 400

    def test_upload_rejects_too_many_files(self, client):
        files = [("files[]", self._make_py_file(f"f{i}.py")) for i in range(6)]
        resp = client.post("/api/projects/upload", files=files)
        # ST-9: upload validation returns 400 for excess files
        assert resp.status_code == 400

    def test_upload_rejects_oversized_file(self, client):
        big_content = b"x = 1\n" * (20 * 1024)  # ~120 KB
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", ("big.py", io.BytesIO(big_content), "text/x-python"))],
        )
        # ST-9: upload validation returns 400 for oversized files
        assert resp.status_code == 400

    def test_upload_result_shape(self, client):
        resp = client.post(
            "/api/projects/upload",
            files=[("files[]", self._make_py_file())],
        )
        data = resp.json()
        assert list(data.keys()) == ["session_file_paths"]


# ---------------------------------------------------------------------------
# ST-1 regression: health endpoint still works after ST-3 changes
# ---------------------------------------------------------------------------

class TestHealthRegressionST1:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_body(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "devproof-ai"


# ---------------------------------------------------------------------------
# Sample project files exist on disk
# ---------------------------------------------------------------------------

class TestSampleProjectFiles:
    _base = Path(__file__).resolve().parent.parent / "sample_projects"

    def test_order_service_python_file_exists(self):
        assert (self._base / "order_service" / "order_service.py").is_file()

    def test_order_service_manifest_exists(self):
        assert (self._base / "order_service" / "project.json").is_file()

    def test_auth_service_python_file_exists(self):
        assert (self._base / "auth_service" / "auth.py").is_file()

    def test_auth_service_manifest_exists(self):
        assert (self._base / "auth_service" / "project.json").is_file()

    def test_order_service_contains_bug_comment(self):
        src = (self._base / "order_service" / "order_service.py").read_text()
        assert "BUG" in src

    def test_auth_service_contains_bug_comment(self):
        src = (self._base / "auth_service" / "auth.py").read_text()
        assert "BUG" in src
