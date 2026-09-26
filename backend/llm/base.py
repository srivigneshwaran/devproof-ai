"""
DevProof AI — LLM provider abstract base class.

ST-2: Defines the common interface that all LLM providers must implement.
Workflow code must never import a provider SDK directly; use this interface.
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Every provider must implement ``complete()``, which accepts a list of
    chat messages and returns the model's text response.
    """

    @abstractmethod
    def complete(
        self,
        messages: list[dict],  # [{"role": "system"|"user", "content": str}]
        json_mode: bool = False,
    ) -> str:
        """Send *messages* to the model and return the response text.

        Args:
            messages: Conversation turns in OpenAI-style format.
                Each entry must have ``"role"`` (``"system"`` or ``"user"``)
                and ``"content"`` (string).
            json_mode: When *True* the caller expects the response to be
                valid JSON. Providers that support a native JSON mode should
                activate it; others must still return parseable JSON text.

        Returns:
            The model's response as a plain string.  When *json_mode* is
            *True* this must be a valid JSON string.
        """
        ...
