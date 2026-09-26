"""
Auth Service — sample project for DevProof AI.

Bug (intentional): token expiry check uses >= instead of >, so a token whose
expiry timestamp equals the current timestamp is incorrectly accepted as valid.

A token should be considered expired when:
    current_time >= expiry                 # correct: expired at or after expiry
    i.e. valid only when current_time < expiry

Buggy check:
    return current_time > expiry           # misses the boundary: == expiry is accepted
"""

import time
from typing import Optional


def create_token(user_id: str, ttl_seconds: int = 3600) -> dict:
    """
    Create a token dict with an expiry timestamp.

    Args:
        user_id:     Identifier for the token owner.
        ttl_seconds: Time-to-live in seconds (default 1 hour).

    Returns:
        Token dict: {"user_id": str, "issued_at": float, "expires_at": float}
    """
    now = time.time()
    return {
        "user_id": user_id,
        "issued_at": now,
        "expires_at": now + ttl_seconds,
    }


def is_token_valid(token: dict, current_time: Optional[float] = None) -> bool:
    """
    Return True if the token is not yet expired.

    BUG: uses strict > comparison, so a token whose expires_at equals
    current_time is incorrectly treated as valid (it should be expired).

    Args:
        token:        Token dict with an 'expires_at' key.
        current_time: Unix timestamp to compare against (defaults to now).

    Returns:
        True if the token is still valid, False if expired.
    """
    if current_time is None:
        current_time = time.time()

    # BUG: should be `current_time >= token["expires_at"]` for the expired branch,
    # i.e. valid when `current_time < token["expires_at"]`.
    # The condition below accepts a token when current_time == expires_at.
    return current_time > token["expires_at"]   # BUG: inverted AND wrong boundary


def get_user_from_token(token: dict, current_time: Optional[float] = None) -> Optional[str]:
    """
    Return the user_id if the token is valid, otherwise None.
    """
    if is_token_valid(token, current_time):
        return token["user_id"]
    return None
