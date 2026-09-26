"""
DevProof AI — LLM provider factory.

ST-2: Reads the ``LLM_PROVIDER`` environment variable and returns the
corresponding ``LLMProvider`` instance.

Supported values for LLM_PROVIDER
-----------------------------------
mock      MockProvider  — offline, no credentials needed (default)
watsonx   WatsonxProvider — IBM watsonx.ai
openai    OpenAIProvider  — OpenAI API

Raises
------
ValueError
    If ``LLM_PROVIDER`` is set to an unsupported value.
"""

import os

from .base import LLMProvider


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
