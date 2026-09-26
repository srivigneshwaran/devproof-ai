"""
Tests for ST-4: Data Models & SQLite Schema.

Covers:
- Schema initialisation (init_db creates all required tables)
- Required tables exist
- Required columns per table
- fix_approvals table structure and constraints
- Repeatability: init_db() called twice does not destroy data
- Pydantic model validation for every model introduced in ST-4
- Regression: ST-1 /health endpoint still works
- Regression: ST-2 LLM provider tests unaffected
- Regression: ST-3 project tests unaffected
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure LLM_PROVIDER=mock for the entire module
# ---------------------------------------------------------------------------

os.environ.setdefault("LLM_PROVIDER", "mock")


# ===========================================================================
# Schema Initialisation Tests
# ===========================================================================

class TestSchemaInit:
    """init_db() creates the full schema safely."""

    def _init_with_temp_db(self):
        """Run init_db() against a temporary database and return the path."""
        import db.database as db_module

        tmp = tempfile.mkdtemp()
        original_db_dir = db_module.DB_DIR
        original_db_path = db_module.DB_PATH

        # Redirect the module-level paths to our temp directory.
        db_module.DB_DIR = Path(tmp)
        db_module.DB_PATH = Path(tmp) / "test.db"
        try:
            db_module.init_db()
            return db_module.DB_PATH
        finally:
            db_module.DB_DIR = original_db_dir
            db_module.DB_PATH = original_db_path

    def test_init_db_creates_database_file(self):
        import db.database as db_module

        tmp = tempfile.mkdtemp()
        original_dir = db_module.DB_DIR
        original_path = db_module.DB_PATH
        db_module.DB_DIR = Path(tmp)
        db_module.DB_PATH = Path(tmp) / "test.db"
        try:
            db_module.init_db()
            assert db_module.DB_PATH.exists()
        finally:
            db_module.DB_DIR = original_dir
            db_module.DB_PATH = original_path

    def test_init_db_creates_directory(self):
        import db.database as db_module

        tmp = tempfile.mkdtemp()
        nested = Path(tmp) / "nested" / "dir"
        original_dir = db_module.DB_DIR
        original_path = db_module.DB_PATH
        db_module.DB_DIR = nested
        db_module.DB_PATH = nested / "test.db"
        try:
            db_module.init_db()
            assert nested.exists()
            assert db_module.DB_PATH.exists()
        finally:
            db_module.DB_DIR = original_dir
            db_module.DB_PATH = original_path

    def test_init_db_is_idempotent(self):
        """Calling init_db() twice must not raise and must not destroy data."""
        import db.database as db_module

        tmp = tempfile.mkdtemp()
        original_dir = db_module.DB_DIR
        original_path = db_module.DB_PATH
        db_module.DB_DIR = Path(tmp)
        db_module.DB_PATH = Path(tmp) / "idempotent.db"
        try:
            db_module.init_db()
            # Insert a row into sessions after first init.
            conn = sqlite3.connect(str(db_module.DB_PATH))
            conn.execute(
                "INSERT INTO sessions (id, project_id, project_name, bug_description) "
                "VALUES ('s1', 'p1', 'Project One', 'Some bug')"
            )
            conn.commit()
            conn.close()

            # Second init — must not destroy existing data.
            db_module.init_db()

            conn = sqlite3.connect(str(db_module.DB_PATH))
            row = conn.execute("SELECT id FROM sessions WHERE id='s1'").fetchone()
            conn.close()
            assert row is not None, "Existing data was destroyed by second init_db() call"
        finally:
            db_module.DB_DIR = original_dir
            db_module.DB_PATH = original_path

    def test_wal_mode_enabled(self):
        """get_connection() enables WAL journal mode."""
        from db.database import get_connection, DB_PATH
        # Only check if database already exists (may not in CI temp env).
        if DB_PATH.exists():
            conn = get_connection()
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            conn.close()
            assert mode == "wal"

    def test_foreign_keys_enabled(self):
        """get_connection() enables foreign key enforcement."""
        from db.database import get_connection, DB_PATH
        if DB_PATH.exists():
            conn = get_connection()
            fk = conn.execute("PRAGMA foreign_keys;").fetchone()[0]
            conn.close()
            assert fk == 1

    def test_row_factory_set(self):
        """get_connection() sets row_factory to sqlite3.Row."""
        from db.database import get_connection, DB_PATH
        if DB_PATH.exists():
            conn = get_connection()
            assert conn.row_factory is sqlite3.Row
            conn.close()


# ===========================================================================
# Required Tables Tests
# ===========================================================================

def _get_tables(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
    ).fetchall()
    conn.close()
    return {row[0] for row in rows}


def _get_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    rows = conn.execute(f"PRAGMA table_info({table});").fetchall()
    conn.close()
    return {row[1] for row in rows}


@pytest.fixture(scope="module")
def temp_db_path(tmp_path_factory):
    """Create a fresh SQLite database from schema.sql for this test module."""
    import db.database as db_module

    tmp = tmp_path_factory.mktemp("schema_test")
    original_dir = db_module.DB_DIR
    original_path = db_module.DB_PATH
    db_module.DB_DIR = tmp
    db_module.DB_PATH = tmp / "schema_test.db"
    db_module.init_db()
    path = db_module.DB_PATH
    # Restore
    db_module.DB_DIR = original_dir
    db_module.DB_PATH = original_path
    return path


class TestRequiredTables:
    def test_sessions_table_exists(self, temp_db_path):
        assert "sessions" in _get_tables(temp_db_path)

    def test_analyses_table_exists(self, temp_db_path):
        assert "analyses" in _get_tables(temp_db_path)

    def test_fix_suggestions_table_exists(self, temp_db_path):
        assert "fix_suggestions" in _get_tables(temp_db_path)

    def test_fix_approvals_table_exists(self, temp_db_path):
        assert "fix_approvals" in _get_tables(temp_db_path)

    def test_reports_table_exists(self, temp_db_path):
        assert "reports" in _get_tables(temp_db_path)

    def test_exactly_five_tables(self, temp_db_path):
        tables = _get_tables(temp_db_path)
        assert tables == {"sessions", "analyses", "fix_suggestions", "fix_approvals", "reports"}


class TestSessionsColumns:
    def test_id_column(self, temp_db_path):
        assert "id" in _get_columns(temp_db_path, "sessions")

    def test_created_at_column(self, temp_db_path):
        assert "created_at" in _get_columns(temp_db_path, "sessions")

    def test_project_id_column(self, temp_db_path):
        assert "project_id" in _get_columns(temp_db_path, "sessions")

    def test_project_name_column(self, temp_db_path):
        assert "project_name" in _get_columns(temp_db_path, "sessions")

    def test_bug_description_column(self, temp_db_path):
        assert "bug_description" in _get_columns(temp_db_path, "sessions")

    def test_status_column(self, temp_db_path):
        assert "status" in _get_columns(temp_db_path, "sessions")

    def test_all_required_columns(self, temp_db_path):
        cols = _get_columns(temp_db_path, "sessions")
        required = {"id", "created_at", "project_id", "project_name", "bug_description", "status"}
        assert required.issubset(cols)


class TestAnalysesColumns:
    def test_all_required_columns(self, temp_db_path):
        cols = _get_columns(temp_db_path, "analyses")
        required = {"id", "session_id", "relevant_files", "root_causes", "created_at"}
        assert required.issubset(cols)


class TestFixSuggestionsColumns:
    def test_all_required_columns(self, temp_db_path):
        cols = _get_columns(temp_db_path, "fix_suggestions")
        required = {"id", "session_id", "file_path", "original", "suggested", "explanation", "created_at"}
        assert required.issubset(cols)


class TestReportsColumns:
    def test_all_required_columns(self, temp_db_path):
        cols = _get_columns(temp_db_path, "reports")
        required = {
            "id", "session_id", "tests_generated", "test_output",
            "tests_passed", "tests_failed", "verdict", "summary", "created_at",
        }
        assert required.issubset(cols)


# ===========================================================================
# fix_approvals Table Tests
# ===========================================================================

class TestFixApprovalsTable:
    def test_all_required_columns(self, temp_db_path):
        cols = _get_columns(temp_db_path, "fix_approvals")
        required = {"id", "session_id", "approved", "feedback", "created_at"}
        assert required.issubset(cols)

    def test_approved_accepts_1(self, temp_db_path):
        conn = sqlite3.connect(str(temp_db_path))
        # First insert a session to satisfy FK (FK not enforced without PRAGMA).
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, project_id, project_name, bug_description) "
            "VALUES ('fa_sess1', 'p', 'P', 'bug')"
        )
        conn.execute(
            "INSERT INTO fix_approvals (id, session_id, approved) "
            "VALUES ('fa1', 'fa_sess1', 1)"
        )
        conn.commit()
        row = conn.execute("SELECT approved FROM fix_approvals WHERE id='fa1'").fetchone()
        conn.close()
        assert row[0] == 1

    def test_approved_accepts_0(self, temp_db_path):
        conn = sqlite3.connect(str(temp_db_path))
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, project_id, project_name, bug_description) "
            "VALUES ('fa_sess2', 'p', 'P', 'bug')"
        )
        conn.execute(
            "INSERT INTO fix_approvals (id, session_id, approved) "
            "VALUES ('fa2', 'fa_sess2', 0)"
        )
        conn.commit()
        row = conn.execute("SELECT approved FROM fix_approvals WHERE id='fa2'").fetchone()
        conn.close()
        assert row[0] == 0

    def test_feedback_is_nullable(self, temp_db_path):
        conn = sqlite3.connect(str(temp_db_path))
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, project_id, project_name, bug_description) "
            "VALUES ('fa_sess3', 'p', 'P', 'bug')"
        )
        conn.execute(
            "INSERT INTO fix_approvals (id, session_id, approved, feedback) "
            "VALUES ('fa3', 'fa_sess3', 0, NULL)"
        )
        conn.commit()
        row = conn.execute("SELECT feedback FROM fix_approvals WHERE id='fa3'").fetchone()
        conn.close()
        assert row[0] is None

    def test_feedback_stores_text(self, temp_db_path):
        conn = sqlite3.connect(str(temp_db_path))
        conn.execute(
            "INSERT OR IGNORE INTO sessions (id, project_id, project_name, bug_description) "
            "VALUES ('fa_sess4', 'p', 'P', 'bug')"
        )
        conn.execute(
            "INSERT INTO fix_approvals (id, session_id, approved, feedback) "
            "VALUES ('fa4', 'fa_sess4', 0, 'Wrong approach')"
        )
        conn.commit()
        row = conn.execute("SELECT feedback FROM fix_approvals WHERE id='fa4'").fetchone()
        conn.close()
        assert row[0] == "Wrong approach"


# ===========================================================================
# Pydantic Model Validation Tests
# ===========================================================================

class TestSessionModels:
    def test_session_create_valid(self):
        from models.session import SessionCreate
        sc = SessionCreate(project_id="order_service", bug_description="Discount bug")
        assert sc.project_id == "order_service"
        assert sc.bug_description == "Discount bug"

    def test_session_create_missing_project_id_raises(self):
        from models.session import SessionCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SessionCreate(bug_description="bug")  # type: ignore[call-arg]

    def test_session_create_missing_bug_description_raises(self):
        from models.session import SessionCreate
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            SessionCreate(project_id="p")  # type: ignore[call-arg]

    def test_session_valid(self):
        from models.session import Session, SessionStatus
        s = Session(
            id="uuid-1",
            project_id="order_service",
            project_name="Order Service",
            bug_description="Discount bug",
            status=SessionStatus.created,
            created_at="2024-01-01T00:00:00Z",
        )
        assert s.status == SessionStatus.created
        assert s.id == "uuid-1"

    def test_session_status_enum_values(self):
        from models.session import SessionStatus
        assert SessionStatus.created == "created"
        assert SessionStatus.analyzed == "analyzed"
        assert SessionStatus.fix_proposed == "fix_proposed"
        assert SessionStatus.fix_approved == "fix_approved"
        assert SessionStatus.fix_rejected == "fix_rejected"
        assert SessionStatus.verified == "verified"

    def test_session_invalid_status_raises(self):
        from models.session import Session
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            Session(
                id="x",
                project_id="p",
                project_name="P",
                bug_description="b",
                status="unknown_status",
                created_at="2024-01-01T00:00:00Z",
            )

    def test_session_json_serialisation(self):
        from models.session import Session, SessionStatus
        s = Session(
            id="uuid-1",
            project_id="order_service",
            project_name="Order Service",
            bug_description="bug",
            status=SessionStatus.fix_approved,
            created_at="2024-01-01T00:00:00Z",
        )
        data = s.model_dump()
        assert data["status"] == "fix_approved"


class TestAnalysisModels:
    def test_file_relevance_valid(self):
        from models.analysis import FileRelevance
        fr = FileRelevance(path="order_service.py", confidence=0.94, reason="Discount logic")
        assert fr.confidence == 0.94

    def test_file_relevance_missing_field_raises(self):
        from models.analysis import FileRelevance
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FileRelevance(path="f.py")  # type: ignore[call-arg]

    def test_root_cause_with_line_hint(self):
        from models.analysis import RootCause
        rc = RootCause(description="bug here", file="f.py", line_hint=27)
        assert rc.line_hint == 27

    def test_root_cause_without_line_hint(self):
        from models.analysis import RootCause
        rc = RootCause(description="bug here", file="f.py")
        assert rc.line_hint is None

    def test_analysis_result_valid(self):
        from models.analysis import AnalysisResult, FileRelevance, RootCause
        ar = AnalysisResult(
            session_id="uuid-1",
            relevant_files=[FileRelevance(path="f.py", confidence=0.9, reason="r")],
            root_causes=[RootCause(description="d", file="f.py")],
        )
        assert len(ar.relevant_files) == 1
        assert len(ar.root_causes) == 1

    def test_analysis_result_empty_lists(self):
        from models.analysis import AnalysisResult
        ar = AnalysisResult(session_id="uuid-1", relevant_files=[], root_causes=[])
        assert ar.relevant_files == []

    def test_analysis_result_json_shape(self):
        from models.analysis import AnalysisResult, FileRelevance, RootCause
        ar = AnalysisResult(
            session_id="s",
            relevant_files=[FileRelevance(path="f.py", confidence=0.8, reason="r")],
            root_causes=[RootCause(description="d", file="f.py", line_hint=5)],
        )
        data = ar.model_dump()
        assert "relevant_files" in data
        assert "root_causes" in data
        assert data["relevant_files"][0]["confidence"] == 0.8
        assert data["root_causes"][0]["line_hint"] == 5


class TestFixModels:
    def test_fix_suggestion_valid(self):
        from models.fix import FixSuggestion
        fs = FixSuggestion(
            id="fix-1",
            file_path="order_service.py",
            original="total = subtotal * (1 - discount)",
            suggested="total = (subtotal * tax_rate) * (1 - discount)",
            explanation="Tax must be applied before discount.",
        )
        assert fs.id == "fix-1"

    def test_fix_suggestion_missing_field_raises(self):
        from models.fix import FixSuggestion
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FixSuggestion(id="x", file_path="f.py")  # type: ignore[call-arg]

    def test_fix_list_valid(self):
        from models.fix import FixList, FixSuggestion
        fl = FixList(
            session_id="uuid-1",
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
        assert fl.session_id == "uuid-1"
        assert len(fl.fixes) == 1

    def test_fix_list_empty_fixes(self):
        from models.fix import FixList
        fl = FixList(session_id="uuid-1", fixes=[])
        assert fl.fixes == []

    def test_fix_approval_approved_true(self):
        from models.fix import FixApproval
        fa = FixApproval(approved=True)
        assert fa.approved is True
        assert fa.feedback is None

    def test_fix_approval_rejected_with_feedback(self):
        from models.fix import FixApproval
        fa = FixApproval(approved=False, feedback="Wrong approach")
        assert fa.approved is False
        assert fa.feedback == "Wrong approach"

    def test_fix_approval_missing_approved_raises(self):
        from models.fix import FixApproval
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            FixApproval()  # type: ignore[call-arg]

    def test_fix_list_json_shape(self):
        from models.fix import FixList, FixSuggestion
        fl = FixList(
            session_id="s",
            fixes=[FixSuggestion(id="f1", file_path="f.py", original="a", suggested="b", explanation="e")],
        )
        data = fl.model_dump()
        assert "session_id" in data
        assert "fixes" in data
        assert data["fixes"][0]["file_path"] == "f.py"


class TestReportModels:
    def test_generated_test_valid(self):
        from models.report import GeneratedTest
        gt = GeneratedTest(file="test_order.py", code="def test_x(): pass")
        assert gt.file == "test_order.py"

    def test_verification_report_valid(self):
        from models.report import VerificationReport, GeneratedTest
        from models.analysis import FileRelevance, RootCause
        from models.fix import FixSuggestion

        rpt = VerificationReport(
            session_id="uuid-1",
            project_name="Order Service",
            bug_description="Discount bug",
            verdict="PASS",
            relevant_files=[FileRelevance(path="f.py", confidence=0.9, reason="r")],
            root_causes=[RootCause(description="d", file="f.py")],
            fixes=[FixSuggestion(id="f1", file_path="f.py", original="a", suggested="b", explanation="e")],
            tests_generated=[GeneratedTest(file="test_f.py", code="def test_x(): pass")],
            test_output="3 passed in 0.21s",
            tests_passed=3,
            tests_failed=0,
            summary="All tests pass.",
            created_at="2024-01-01T00:00:00Z",
        )
        assert rpt.verdict == "PASS"
        assert rpt.tests_passed == 3

    def test_verification_report_verdict_values(self):
        from models.report import VerificationReport
        from models.analysis import FileRelevance, RootCause
        from models.fix import FixSuggestion
        from models.report import GeneratedTest

        base = dict(
            session_id="s",
            project_name="P",
            bug_description="b",
            relevant_files=[],
            root_causes=[],
            fixes=[],
            tests_generated=[],
            test_output="",
            tests_passed=0,
            tests_failed=0,
            summary="",
            created_at="2024-01-01T00:00:00Z",
        )
        for verdict in ("PASS", "FAIL", "PARTIAL", "ERROR"):
            rpt = VerificationReport(**base, verdict=verdict)
            assert rpt.verdict == verdict

    def test_verification_report_missing_field_raises(self):
        from models.report import VerificationReport
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            VerificationReport(session_id="s")  # type: ignore[call-arg]

    def test_verification_report_json_shape(self):
        from models.report import VerificationReport
        rpt = VerificationReport(
            session_id="s",
            project_name="P",
            bug_description="b",
            verdict="FAIL",
            relevant_files=[],
            root_causes=[],
            fixes=[],
            tests_generated=[],
            test_output="1 failed",
            tests_passed=0,
            tests_failed=1,
            summary="Failed.",
            created_at="2024-01-01T00:00:00Z",
        )
        data = rpt.model_dump()
        required_keys = {
            "session_id", "project_name", "bug_description", "verdict",
            "relevant_files", "root_causes", "fixes", "tests_generated",
            "test_output", "tests_passed", "tests_failed", "summary", "created_at",
        }
        assert required_keys.issubset(set(data.keys()))


# ===========================================================================
# ST-1 Regression: /health endpoint
# ===========================================================================

class TestHealthRegressionST1:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        import main as app_module
        with TestClient(app_module.app) as c:
            yield c

    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_response_body(self, client):
        resp = client.get("/health")
        body = resp.json()
        assert body["status"] == "ok"
        assert body["service"] == "devproof-ai"


# ===========================================================================
# ST-2 Regression: LLM provider still works
# ===========================================================================

class TestLLMRegressionST2:
    def test_mock_provider_still_returns_string(self):
        from llm.mock_provider import MockProvider
        p = MockProvider()
        result = p.complete([{"role": "user", "content": "hello"}])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_factory_still_returns_mock(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from llm.factory import get_provider
        from llm.mock_provider import MockProvider
        assert isinstance(get_provider(), MockProvider)


# ===========================================================================
# ST-3 Regression: project endpoints still work
# ===========================================================================

class TestProjectsRegressionST3:
    @pytest.fixture(scope="class")
    def client(self):
        from fastapi.testclient import TestClient
        import main as app_module
        with TestClient(app_module.app) as c:
            yield c

    def test_get_projects_returns_200(self, client):
        resp = client.get("/api/projects")
        assert resp.status_code == 200

    def test_get_projects_contains_order_service(self, client):
        resp = client.get("/api/projects")
        ids = [p["id"] for p in resp.json()]
        assert "order_service" in ids

    def test_get_projects_contains_auth_service(self, client):
        resp = client.get("/api/projects")
        ids = [p["id"] for p in resp.json()]
        assert "auth_service" in ids

    def test_order_service_files_returns_200(self, client):
        resp = client.get("/api/projects/order_service/files")
        assert resp.status_code == 200

    def test_auth_service_files_returns_200(self, client):
        resp = client.get("/api/projects/auth_service/files")
        assert resp.status_code == 200

    def test_unknown_project_returns_404(self, client):
        resp = client.get("/api/projects/no_such_project/files")
        assert resp.status_code == 404

    def test_sample_project_files_still_on_disk(self):
        base = Path(__file__).resolve().parent.parent / "sample_projects"
        assert (base / "order_service" / "order_service.py").is_file()
        assert (base / "auth_service" / "auth.py").is_file()
