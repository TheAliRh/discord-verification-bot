"""
OAuth2 state-token store.

Discord's OAuth2 "state" parameter round-trips through the user's browser
and back to our callback route unchanged, so it serves two purposes here:
  1. CSRF protection (the standard reason state exists at all)
  2. The ONLY way our stateless HTTP callback route knows which Discord
     guild/user a given authorization attempt belongs to, since there's
     no Discord interaction object on that side of the flow.
"""

import secrets
import time
from typing import Any

_STATES: dict[str, dict[str, Any]] = {}
_TTL_SECONDS = 600  # OAuth flows can take longer than typing a captcha code


def create_state(guild_id: int, user_id: int) -> str:
    _cleanup_expired()
    token = secrets.token_urlsafe(24)
    _STATES[token] = {
        "guild_id": guild_id,
        "user_id": user_id,
        "expires_at": time.time() + _TTL_SECONDS,
    }
    return token


def consume_state(token: str) -> dict[str, Any] | None:
    """Single-use: pops the entry so a state token can't be replayed."""
    entry = _STATES.pop(token, None)
    if entry is None:
        return None
    if time.time() > entry["expires_at"]:
        return None
    return entry


def _cleanup_expired() -> None:
    now = time.time()
    expired = [t for t, e in _STATES.items() if e["expires_at"] < now]
    for t in expired:
        _STATES.pop(t, None)
