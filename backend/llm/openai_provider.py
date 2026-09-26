"""
DevProof AI — OpenAI LLM provider.

ST-2: Wraps the ``openai`` SDK behind the ``LLMProvider`` interface.
All configuration is read from environment variables; no credentials are
hard-coded here.

Required environment variables
-------------------------------
OPENAI_API_KEY       OpenAI secret key

Optional environment variables
-------------------------------
LLM_MODEL            Model ID string used for the chat completion call.
                     There is no default; the environment must specify the
                     model explicitly (e.g. gpt-4o, gpt-4o-mini, gpt-3.5-turbo).
OPENAI_BASE_URL      Override the API base URL (useful for Azure OpenAI or
                     compatible endpoints).
"""

import os

from .base import LLMProvider


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI API.

    The ``openai`` SDK is imported lazily inside the constructor so that
    the module can be imported even when the package is not installed.
    """

    def __init__(self) -> None:
        # Lazy import — keeps the module importable without the SDK installed.
        try:
            from openai import OpenAI
        except ImportError as exc:
            raise ImportError(
                "openai is required for OpenAIProvider. "
                "Install it with: pip install openai"
            ) from exc

        api_key = os.environ.get("OPENAI_API_KEY")
        model = os.environ.get("LLM_MODEL")
        base_url = os.environ.get("OPENAI_BASE_URL")  # optional

        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")
        if not model:
            raise ValueError(
                "LLM_MODEL environment variable is not set. "
                "Specify a model such as gpt-4o or gpt-4o-mini."
            )

        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url

        self._client = OpenAI(**kwargs)
        self._model = model

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
    ) -> str:
        """Call the OpenAI chat completions endpoint."""
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""
