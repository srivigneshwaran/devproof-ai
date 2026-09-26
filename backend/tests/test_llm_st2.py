"""
Tests for ST-2: LLM Provider Abstraction.

All tests use MockProvider and the factory; no external API credentials are
required to pass this test suite.
"""

import importlib
import json
import os

import pytest


# ---------------------------------------------------------------------------
# LLMProvider ABC
# ---------------------------------------------------------------------------

class TestLLMProviderABC:
    def test_cannot_instantiate_directly(self):
        from llm.base import LLMProvider

        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_complete_is_abstract(self):
        from llm.base import LLMProvider
        import inspect

        assert inspect.isabstract(LLMProvider)


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------

class TestMockProvider:
    def _provider(self):
        from llm.mock_provider import MockProvider
        return MockProvider()

    def test_plain_text_response(self):
        p = self._provider()
        result = p.complete([{"role": "user", "content": "hello"}])
        assert isinstance(result, str)
        assert len(result) > 0

    def test_json_mode_returns_valid_json(self):
        p = self._provider()
        result = p.complete([{"role": "user", "content": "hello"}], json_mode=True)
        parsed = json.loads(result)  # must not raise
        assert isinstance(parsed, dict)

    def test_analysis_keyword_triggers_analysis_response(self):
        p = self._provider()
        result = p.complete(
            [{"role": "user", "content": "please analyse this code"}],
            json_mode=True,
        )
        data = json.loads(result)
        assert "relevant_files" in data
        assert "root_causes" in data

    def test_fix_keyword_triggers_fix_response(self):
        p = self._provider()
        result = p.complete(
            [{"role": "user", "content": "suggest a fix for the bug"}],
            json_mode=True,
        )
        data = json.loads(result)
        assert "fixes" in data

    def test_verification_keyword_triggers_verification_response(self):
        p = self._provider()
        result = p.complete(
            [{"role": "user", "content": "generate tests and verify"}],
            json_mode=True,
        )
        data = json.loads(result)
        assert "verdict" in data
        assert data["verdict"] == "PASS"

    def test_unknown_keyword_returns_generic_response(self):
        p = self._provider()
        result = p.complete(
            [{"role": "user", "content": "something completely unrelated"}],
            json_mode=True,
        )
        data = json.loads(result)
        assert "message" in data

    def test_deterministic_responses(self):
        """Same input always produces the same output."""
        p = self._provider()
        messages = [{"role": "user", "content": "analyse the order service"}]
        r1 = p.complete(messages, json_mode=True)
        r2 = p.complete(messages, json_mode=True)
        assert r1 == r2

    def test_implements_llm_provider(self):
        from llm.base import LLMProvider
        from llm.mock_provider import MockProvider

        assert issubclass(MockProvider, LLMProvider)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

class TestFactory:
    def test_factory_returns_mock_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        from llm.factory import get_provider

        provider = get_provider()
        from llm.mock_provider import MockProvider

        assert isinstance(provider, MockProvider)

    def test_factory_returns_mock_when_set_to_mock(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from llm.factory import get_provider
        from llm.mock_provider import MockProvider

        provider = get_provider()
        assert isinstance(provider, MockProvider)

    def test_factory_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "MOCK")
        from llm.factory import get_provider
        from llm.mock_provider import MockProvider

        provider = get_provider()
        assert isinstance(provider, MockProvider)

    def test_factory_raises_for_unknown_provider(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "nonexistent_llm")
        from llm.factory import get_provider

        with pytest.raises(ValueError, match="Unsupported LLM_PROVIDER"):
            get_provider()

    def test_watsonx_provider_requires_credentials(self, monkeypatch):
        """WatsonxProvider raises ValueError when env vars are absent."""
        monkeypatch.setenv("LLM_PROVIDER", "watsonx")
        monkeypatch.delenv("WATSONX_API_KEY", raising=False)
        monkeypatch.delenv("WATSONX_PROJECT_ID", raising=False)
        monkeypatch.delenv("WATSONX_URL", raising=False)
        from llm.factory import get_provider

        # Should raise either ImportError (SDK not installed) or ValueError (missing creds).
        with pytest.raises((ImportError, ValueError)):
            get_provider()

    def test_openai_provider_requires_api_key(self, monkeypatch):
        """OpenAIProvider raises ValueError when OPENAI_API_KEY is absent."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("LLM_MODEL", "gpt-4o-mini")
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        from llm.factory import get_provider

        with pytest.raises((ImportError, ValueError)):
            get_provider()

    def test_openai_provider_requires_model(self, monkeypatch):
        """OpenAIProvider raises ValueError when LLM_MODEL is absent."""
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-fake")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        from llm.factory import get_provider

        with pytest.raises((ImportError, ValueError)):
            get_provider()


# ---------------------------------------------------------------------------
# FastAPI app integration
# ---------------------------------------------------------------------------

class TestAppStateIntegration:
    def test_app_state_llm_is_set(self, monkeypatch):
        """app.state.llm is populated after lifespan startup with mock provider."""
        monkeypatch.setenv("LLM_PROVIDER", "mock")

        from fastapi.testclient import TestClient
        import main as app_module  # type: ignore[import]

        with TestClient(app_module.app) as client:
            from llm.mock_provider import MockProvider
            assert isinstance(app_module.app.state.llm, MockProvider)

    def test_health_endpoint_still_works(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "mock")
        from fastapi.testclient import TestClient
        import main as app_module  # type: ignore[import]

        with TestClient(app_module.app) as client:
            resp = client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"
