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
                from order_service import calculate_order_total

                def test_discount_applied_after_tax():
                    # With the fix: total = subtotal * tax_rate * (1 - discount_rate)
                    # subtotal=100, tax_rate=1.1, discount_rate=0.1
                    # expected = 100 * 1.1 * 0.9 = 99.0
                    assert calculate_order_total(100, 1.1, 0.1) == 99.0

                def test_no_discount():
                    # subtotal=100, tax_rate=1.1, discount_rate=0.0
                    # expected = 100 * 1.1 = 110.0
                    assert calculate_order_total(100, 1.1, 0.0) == 110.0

                def test_full_discount():
                    # subtotal=100, tax_rate=1.1, discount_rate=1.0
                    # expected = 0.0
                    assert calculate_order_total(100, 1.1, 1.0) == 0.0
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

# Plain-text test code returned by MockProvider when json_mode=False and the
# prompt asks to write pytest tests.  This is what test_service.py expects.
_MOCK_TEST_CODE_ORDER = textwrap.dedent(
    """\
    import pytest
    from order_service import calculate_order_total

    def test_discount_applied_after_tax():
        # subtotal=100, tax_rate=1.1, discount_rate=0.1
        # fixed: total = subtotal * tax_rate * (1 - discount_rate) = 99.0
        assert calculate_order_total(100, 1.1, 0.1) == 99.0

    def test_no_discount():
        assert calculate_order_total(100, 1.1, 0.0) == 110.0

    def test_full_discount():
        assert calculate_order_total(100, 1.1, 1.0) == 0.0
    """
)

_MOCK_TEST_CODE_AUTH = textwrap.dedent(
    """\
    import pytest
    from auth import is_token_valid

    def test_token_expired_at_boundary():
        token = {"expires_at": 1000.0}
        # Fixed: current_time >= expires_at means expired
        assert is_token_valid(token, current_time=1000.0) is False

    def test_token_valid_before_expiry():
        token = {"expires_at": 2000.0}
        assert is_token_valid(token, current_time=1000.0) is True

    def test_token_expired_after():
        token = {"expires_at": 1000.0}
        assert is_token_valid(token, current_time=1001.0) is False
    """
)

_MOCK_SUMMARY_TEXT = (
    "The fix was applied successfully and all generated tests pass. "
    "The identified bug has been corrected and verified through automated testing."
)

_GENERIC_RESPONSE: dict = {
    "message": "Mock response — no real LLM call was made.",
    "status": "ok",
}

# Keyword → canned response mapping for JSON-mode calls
# (checked against the last user message).
_JSON_KEYWORD_MAP: list[tuple[str, dict]] = [
    ("analys", _ANALYSIS_RESPONSE),
    ("root cause", _ANALYSIS_RESPONSE),
    ("fix", _FIX_RESPONSE),
    ("patch", _FIX_RESPONSE),
    ("verif", _VERIFICATION_RESPONSE),
    ("test", _VERIFICATION_RESPONSE),
]

# Keyword → canned plain-text response for non-JSON calls.
# Test generation calls use json_mode=False and ask to write pytest code.
_PLAINTEXT_KEYWORD_MAP: list[tuple[str, str]] = [
    ("auth", _MOCK_TEST_CODE_AUTH),
    ("write pytest", _MOCK_TEST_CODE_ORDER),
    ("pytest test", _MOCK_TEST_CODE_ORDER),
    ("test file", _MOCK_TEST_CODE_ORDER),
    ("test_order", _MOCK_TEST_CODE_ORDER),
    ("test_auth", _MOCK_TEST_CODE_AUTH),
    ("summary", _MOCK_SUMMARY_TEXT),
    ("sentence summary", _MOCK_SUMMARY_TEXT),
    ("verif", _MOCK_SUMMARY_TEXT),
]


def _select_json_response(messages: list[dict]) -> dict:
    """Return the most appropriate canned JSON response for *messages*."""
    last_user_content = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            last_user_content = str(msg.get("content", "")).lower()
            break

    for keyword, response in _JSON_KEYWORD_MAP:
        if keyword in last_user_content:
            return response

    return _GENERIC_RESPONSE


def _select_plaintext_response(messages: list[dict]) -> str:
    """Return the most appropriate canned plain-text response for *messages*."""
    # Gather all message content for matching.
    all_content = " ".join(
        str(msg.get("content", "")).lower()
        for msg in messages
    )

    for keyword, response in _PLAINTEXT_KEYWORD_MAP:
        if keyword in all_content:
            return response

    # Default plain-text: generic summary.
    return _MOCK_SUMMARY_TEXT


class MockProvider(LLMProvider):
    """Offline LLM provider for development and testing.

    Returns deterministic canned responses that match the shapes the
    real providers would return.  No API keys or network access required.
    """

    def complete(
        self,
        messages: list[dict],
        json_mode: bool = False,
    ) -> str:
        """Return a deterministic canned response.

        When *json_mode* is *True* the response is always valid JSON.
        When *json_mode* is *False* a plain-text response is returned —
        for test generation prompts this is valid Python test code.
        """
        if json_mode:
            payload = _select_json_response(messages)
            return json.dumps(payload)

        return _select_plaintext_response(messages)
