"""
DevProof AI — LLM exception types (ST-8).

Defines LLMServiceError, the single exception raised by all service-layer
LLM calls when the provider fails.  Routers catch this and map it to HTTP 503.
"""


class LLMServiceError(Exception):
    """Raised when an LLM provider call fails for any reason.

    Attributes:
        message: Human-readable description of the failure.
        original: The underlying exception that caused this error, if any.
    """

    def __init__(self, message: str, original: Exception | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.original = original

    def __str__(self) -> str:
        if self.original is not None:
            return f"{self.message}: {self.original}"
        return self.message
