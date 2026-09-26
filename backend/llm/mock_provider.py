"""
DevProof AI — Mock LLM provider.

ST-2: Returns deterministic, valid JSON-compatible responses so that the
entire backend/frontend stack can be exercised without any external API
credentials.

This provider requires no environment variables and never makes network calls.
It inspects the last user message to select from a small set of canned
responses that mirror the JSON shapes the real providers would return.
"""

import json
import textwrap

from .base import LLMProvider

# ---------------------------------------------------------------------------
# Canned response catalogue
# Every value is a JSON string that matches the shape expected by the future
# service layer.  Service functions always call complete(..., json_mode=True)
# so we return valid JSON for those and plain text for plain calls.
# ---------------------------------------------------------------------------

_ANALYSIS_RESPONSE: dict = {
    "relevant_files": [
        {
            "path": "order_service.py",
            "confidence": 0.94,
            "reason": "Discount logic is applied before tax calculation.",
        }
    ],
    "root_causes": [
        {
            "description": "Discount is applied to pre-tax subtotal instead of post-tax total.",
            "file": "order_service.py",
            "line_hint": 27,
        }
    ],
}

_FIX_RESPONSE: dict = {
    "fixes": [
        {
            "file_path": "order_service.py",
            "original": "total = round((subtotal - discount_amount) * tax_rate, 2)",
            "suggested": "total = round(subtotal * tax_rate * (1 - discount_rate), 2)",
            "explanation": (
                "Tax must be applied before discount to match pricing rules. "
                "The corrected formula first multiplies the subtotal by the tax rate "
                "and then applies the discount percentage to the post-tax amount."
            ),
        }
    ]
}

_VERIFICATION_RESPONSE: dict = {
    "verdict": "PASS",
    "tests_generated": [
        {
            "file": "test_order_service.py",
            "code": textwrap.dedent(
                """\
                import pytest
                from order_service import calculate_total

                def test_discount_applied_after_tax():
                    assert calculate_total(100, 0.10, 0.20) == 108.0

                def test_no_discount():
                    assert calculate_total(100, 0.0, 0.20) == 120.0

                def test_full_discount():
                    assert calculate_total(100, 1.0, 0.20) == 0.0
                """
            ),
        }
    ],
    "test_output": "3 passed in 0.05s",
    "tests_passed": 3,
    "tests_failed": 0,
    "summary": (
        "The discount/tax ordering bug in order_service.py was corrected. "
        "All 3 generated tests pass."
    ),
}

_GENERIC_RESPONSE: dict = {
    "message": "Mock response — no real LLM call was made.",
    "status": "ok",
}

# Keyword → canned response mapping (checked against the last user message).
_KEYWORD_MAP: list[tuple[str, dict]] = [
    ("analys", _ANALYSIS_RESPONSE),
    ("root cause", _ANALYSIS_RESPONSE),
    ("fix", _FIX_RESPONSE),
    ("patch", _FIX_RESPONSE),
    ("test", _VERIFICATION_RESPONSE),
    ("verif", _VERIFICATION_RESPONSE),
]


def _select_response(messages: list[dict]) -> dict:
    """Return the most appropriate canned response for *messages*."""
    last_user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_content = str(msg.get("content", "")).lower()
            break

    for keyword, response in _KEYWORD_MAP:
        if keyword in last_user_content:
            return response

    return _GENERIC_RESPONSE


class MockProvider(LLMProvider):
    """Offline LLM provider for development and testing.

    Returns deterministic canned JSON responses that match the shapes the
    real providers would return.  No API keys or network access required.
    """

    def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
    ) -> str:
        """Return a deterministic canned response.

        When *json_mode* is *True* the response is always valid JSON.
        When *json_mode* is *False* a plain-text summary is returned.
        """
        payload = _select_response(messages)

        if json_mode:
            return json.dumps(payload)

        # Plain-text mode: return a readable summary.
        return (
            "[MockProvider] "
            + "; ".join(f"{k}={v!r}" for k, v in list(payload.items())[:2])
        )
