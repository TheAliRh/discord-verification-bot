"""
Shared captcha challenge store.

Any captcha-style module (text-in-modal, image-based, future audio, etc.)
needs the same three things: generate a code, remember it against a user
with an expiry, and check an answer against it. Keeping that logic in one
place means every captcha variant behaves identically underneath - only
how the code is *shown* to the user differs per module.

Challenges are keyed by (guild_id, user_id), not just user_id. This bot
serves multiple guilds at once, so the same Discord user could click
Verify in two different servers around the same time; keying by user_id
alone would let the second server's challenge silently overwrite (and
invalidate) the first server's still-pending one.

In-memory only: fine for a single-process bot. If you ever run multiple
processes/shards sharing state, swap this for Redis or the DB.
"""

import random
import string
import time
from typing import Any

_CHALLENGES: dict[tuple[int, int], dict[str, Any]] = (
    {}
)  # (guild_id, user_id) -> {code, expires_at}
_DEFAULT_TTL_SECONDS = 300

# Characters that are easy to confuse (0/O, 1/I) are excluded from every captcha variant.
_SAFE_ALPHANUMERIC = "".join(
    c for c in string.ascii_uppercase + string.digits if c not in "0O1I"
)
_SAFE_NUMERIC = "".join(c for c in string.digits if c not in "01")


def generate_code(length: int = 6, kind: str = "alphanumeric") -> str:
    alphabet = _SAFE_NUMERIC if kind == "numeric" else _SAFE_ALPHANUMERIC
    return "".join(random.choices(alphabet, k=length))


def store_challenge(
    guild_id: int, user_id: int, code: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS
) -> None:
    _cleanup_expired()
    _CHALLENGES[(guild_id, user_id)] = {
        "code": code,
        "expires_at": time.time() + ttl_seconds,
    }


def check_answer(guild_id: int, user_id: int, answer: str) -> tuple[bool, str | None]:
    """
    Consumes the stored challenge (pass or fail) so each generated code is
    single-use - a fresh click of Verify is required to try again.
    Returns (passed, failure_reason). failure_reason is None on success.
    """
    entry = _CHALLENGES.pop((guild_id, user_id), None)

    if entry is None:
        return False, "No active code found. Click Verify to get a new one."
    if time.time() > entry["expires_at"]:
        return False, "That code expired."
    if answer.strip().upper() == entry["code"]:
        return True, None
    return False, "That code didn't match."


def _cleanup_expired() -> None:
    now = time.time()
    expired = [key for key, entry in _CHALLENGES.items() if entry["expires_at"] < now]
    for key in expired:
        _CHALLENGES.pop(key, None)
