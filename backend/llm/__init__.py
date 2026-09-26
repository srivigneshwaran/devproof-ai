"""
DevProof AI — llm package public API.

ST-2: Exposes the LLMProvider base class and the factory function so that
service modules only need to import from this package.
"""

from .base import LLMProvider
from .factory import get_provider

__all__ = ["LLMProvider", "get_provider"]
