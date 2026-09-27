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
            "reason": "Coupon discount is applied before tax, reducing the taxable base.",
        }
    ],
    "root_causes": [
        {
            "description": (
                "coupon_discount is subtracted from subtotal before tax is applied. "
                "It should be subtracted after tax so the full subtotal is taxed."
            ),
            "file": "order_service.py",
            "line_hint": 42,
        }
    ],
}

_FIX_RESPONSE: dict = {
    "fixes": [
        {
            "file_path": "order_service.py",
            "original": "    total = round((subtotal - coupon_discount) * tax_rate, 2)  # BUG: discount before tax",
            "suggested": "    total = round(subtotal * tax_rate - coupon_discount, 2)",
            "explanation": (
                "The coupon discount must be applied after tax, not before. "
                "Applying it before tax reduces the taxable base and causes the "
                "customer to be charged less than the correct post-tax amount minus coupon."
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

                def test_coupon_applied_after_tax():
                    # subtotal=100, tax_rate=1.1, coupon=10
                    # fixed:  100 * 1.1 - 10 = 100.0
                    # buggy: (100 - 10) * 1.1 = 99.0
                    assert calculate_order_total(100, 1.1, 10) == 100.0

                def test_no_coupon():
                    # No coupon: total = subtotal * tax_rate
                    # 100 * 1.1 - 0 = 110.0  (same for both buggy and fixed)
                    assert calculate_order_total(100, 1.1, 0) == 110.0

                def test_large_coupon():
                    # subtotal=200, tax_rate=1.1, coupon=20
                    # fixed:  200 * 1.1 - 20 = 200.0
                    # buggy: (200 - 20) * 1.1 = 198.0
                    assert calculate_order_total(200, 1.1, 20) == 200.0
                """
            ),
        }
    ],
    "test_output": "3 passed in 0.05s",
    "tests_passed": 3,
    "tests_failed": 0,
    "summary": (
        "The coupon-discount ordering bug in order_service.py was corrected. "
        "All 3 generated tests pass with the fix applied."
    ),
}

# Plain-text test code returned by MockProvider when json_mode=False and the
# prompt asks to write pytest tests.  This is what test_service.py expects.
_MOCK_TEST_CODE_ORDER = textwrap.dedent(
    """\
    import pytest
    from order_service import calculate_order_total

    def test_coupon_applied_after_tax():
        # subtotal=100, tax_rate=1.1, coupon=10
        # fixed:  100 * 1.1 - 10 = 100.0
        # buggy: (100 - 10) * 1.1 = 99.0
        assert calculate_order_total(100, 1.1, 10) == 100.0

    def test_no_coupon():
        assert calculate_order_total(100, 1.1, 0) == 110.0

    def test_large_coupon():
        # subtotal=200, tax_rate=1.1, coupon=20
        # fixed:  200 * 1.1 - 20 = 200.0
        # buggy: (200 - 20) * 1.1 = 198.0
        assert calculate_order_total(200, 1.1, 20) == 200.0
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

# Keyword → canned response mapping for JSON-mode calls.
#
# These keywords are matched against the system prompt text only
# (see _select_json_response).  Each keyword must appear in exactly
# one service's system prompt to avoid ambiguous routing.
#
# Analysis system prompt:  "code reviewer and debugger"  → "code reviewer"
# Fix system prompt:       "code repair"                 → "code repair"
# Verify/test system prompt: "test engineer"             → "test engineer"
# (Report uses json_mode=False so it routes via _PLAINTEXT_KEYWORD_MAP)
_JSON_KEYWORD_MAP: list[tuple[str, dict]] = [
    ("code reviewer", _ANALYSIS_RESPONSE),
    ("code repair", _FIX_RESPONSE),
    ("verif", _VERIFICATION_RESPONSE),
    ("test engineer", _VERIFICATION_RESPONSE),
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
    """Return the most appropriate canned JSON response for *messages*.

    Routes by inspecting the **system prompt** only (role == "system").
    System prompts are authored by the service layer and contain unique,
    stable keywords that identify the call type. Routing by user-message
    content is unreliable because file contents uploaded by users or
    included as source context may contain any keyword.
    Falls back to all-message scan if no system prompt is present.
    """
    system_content = ""
    for msg in messages:
        if msg.get("role") == "system":
            system_content = str(msg.get("content", "")).lower()
            break

    # If there is no system message, fall back to the last user message
    # (legacy path, keeps backward-compatibility for direct calls).
    if not system_content:
        for msg in reversed(messages):
            if msg.get("role") == "user":
                system_content = str(msg.get("content", "")).lower()
                break

    for keyword, response in _JSON_KEYWORD_MAP:
        if keyword in system_content:
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
