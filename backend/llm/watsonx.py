"""
DevProof AI — IBM watsonx.ai LLM provider.

ST-2: Wraps the ``ibm-watsonx-ai`` SDK behind the ``LLMProvider`` interface.
All configuration is read from environment variables; no credentials are
hard-coded here.

Required environment variables
-------------------------------
WATSONX_API_KEY      IBM Cloud API key
WATSONX_PROJECT_ID   watsonx.ai project ID
WATSONX_URL          watsonx.ai endpoint URL
                     e.g. https://us-south.ml.cloud.ibm.com

Optional environment variables
-------------------------------
LLM_MODEL            Model ID string (default: ibm/granite-13b-chat-v2)
"""

import json
import os

from .base import LLMProvider


class WatsonxProvider(LLMProvider):
    """LLM provider backed by IBM watsonx.ai.

    The ``ibm-watsonx-ai`` SDK is imported lazily inside the constructor so
    that the module can be imported even when the package is not installed
    (it will only fail at instantiation time).
    """

    def __init__(self) -> None:
        # Lazy import — keeps the module importable without the SDK installed.
        try:
            from ibm_watsonx_ai import APIClient, Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference
        except ImportError as exc:
            raise ImportError(
                "ibm-watsonx-ai is required for WatsonxProvider. "
                "Install it with: pip install ibm-watsonx-ai"
            ) from exc

        api_key = os.environ.get("WATSONX_API_KEY")
        project_id = os.environ.get("WATSONX_PROJECT_ID")
        url = os.environ.get("WATSONX_URL")
        model_id = os.environ.get("LLM_MODEL", "ibm/granite-13b-chat-v2")

        if not api_key:
            raise ValueError("WATSONX_API_KEY environment variable is not set.")
        if not project_id:
            raise ValueError("WATSONX_PROJECT_ID environment variable is not set.")
        if not url:
            raise ValueError("WATSONX_URL environment variable is not set.")

        credentials = Credentials(url=url, api_key=api_key)
        client = APIClient(credentials=credentials, project_id=project_id)

        self._model = ModelInference(
            model_id=model_id,
            api_client=client,
        )
        self._model_id = model_id

    # ------------------------------------------------------------------
    # LLMProvider interface
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
    ) -> str:
        """Call the watsonx.ai chat completion endpoint.

        The SDK's ``chat()`` method accepts the same OpenAI-style messages
        list, so we pass it through directly.
        """
        params: dict = {}
        if json_mode:
            params["response_format"] = {"type": "json_object"}

        response = self._model.chat(messages=messages, params=params if params else None)

        # The SDK returns a dict with choices[0].message.content or similar.
        # Handle both dict and object-style responses defensively.
        if isinstance(response, dict):
            choices = response.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                return msg.get("content", "")
            return json.dumps(response)

        # Object-style response
        return str(response)
