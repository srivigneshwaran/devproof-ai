"""
DevProof AI — LLM provider factory.

ST-2: Reads the ``LLM_PROVIDER`` environment variable and returns the
corresponding ``LLMProvider`` instance.

ST-8: ``validate_env()`` checks that all required environment variables are
present before the application starts, raising ``RuntimeError`` with a clear
human-readable message if anything is missing.

Supported values for LLM_PROVIDER
-----------------------------------
mock      MockProvider  — offline, no credentials needed (default)
watsonx   WatsonxProvider — IBM watsonx.ai
openai    OpenAIProvider  — OpenAI API

Raises
------
ValueError
    If ``LLM_PROVIDER`` is set to an unsupported value.
RuntimeError (from validate_env)
    If required environment variables for the selected provider are absent.
"""

import os

from .base import LLMProvider

# ---------------------------------------------------------------------------
# Required variables per provider
# ---------------------------------------------------------------------------
_PROVIDER_REQUIRED_VARS: dict[str, list[str]] = {
    "watsonx": ["WATSONX_API_KEY", "WATSONX_PROJECT_ID", "WATSONX_URL", "LLM_MODEL"],
    "openai": ["OPENAI_API_KEY", "LLM_MODEL"],
}


def validate_env() -> None:
    """Validate that required environment variables are present.

    Called at application startup (before ``get_provider()``).  For the
    ``mock`` provider no variables are required.  For real providers the
    variables listed in ``_PROVIDER_REQUIRED_VARS`` must all be set and
    non-empty.

    Raises:
        RuntimeError: If any required variable is missing or empty.
    """
    provider_name = os.environ.get("LLM_PROVIDER", "mock").strip().lower()

    # mock provider needs no credentials.
    if provider_name == "mock":
        return

    # Unknown provider — get_provider() will raise a clearer error later.
    required = _PROVIDER_REQUIRED_VARS.get(provider_name)
    if required is None:
        return

    missing = [var for var in required if not os.environ.get(var, "").strip()]
    if missing:
        raise RuntimeError(
            f"Missing required environment variable(s) for LLM_PROVIDER='{provider_name}': "
            + ", ".join(missing)
            + ". Set these in your .env file before starting the server."
        )


def get_provider() -> LLMProvider:
    """Instantiate and return the configured LLM provider.

    The provider is selected by the ``LLM_PROVIDER`` environment variable.
    When the variable is absent, ``mock`` is used so the application starts
    without any external credentials.

    Returns:
        A concrete ``LLMProvider`` instance ready to call.

    Raises:
        ValueError: If ``LLM_PROVIDER`` is set to an unrecognised value.
    """
    provider_name = os.environ.get("LLM_PROVIDER", "mock").strip().lower()

    if provider_name == "mock":
        from .mock_provider import MockProvider

        return MockProvider()

    if provider_name == "watsonx":
        from .watsonx import WatsonxProvider

        return WatsonxProvider()

    if provider_name == "openai":
        from .openai_provider import OpenAIProvider

        return OpenAIProvider()

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider_name}'. "
        "Supported values: mock | watsonx | openai"
    )
