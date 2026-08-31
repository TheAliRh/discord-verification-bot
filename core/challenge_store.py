"""
Shared captcha challenge store.

Any captcha-style module (text-in-modal, image-based, future audio, etc.)
needs the same three things: generate a code, remember it against a user
with an expiry, and check an answer against it. Keeping that logic in one
place means every captcha variant behaves identically underneath - only
how the code is *shown* to the user differs per module.

In-memory only: fine for a single-process bot. If you ever run multiple
processes/shards sharing state, swap this for Redis or the DB.
"""

import random
import string
import time

_CHALLENGES: dict[int, dict] = {}
_DEFAULT_TTL_SECONDS = 300

# Characters that are easy to confuse (0/O, 1/I) are excluded from every captcha variant.
_SAFE_ALPHANUMERIC = "".join(
    c for c in string.ascii_uppercase + string.digits if c not in "0O1I"
)
_SAFE_NUMERIC = "".join(c for c in string.digits if c not in "01")


def generate_code(length: int = 6, kind: str = "alphanumeric") -> str:
    alphabet = _SAFE_NUMERIC if kind == "numeric" else _SAFE_ALPHANUMERIC
    return "".join(random.choices(alphabet, k=length))


def store_challenge(user_id: int, code: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
    _cleanup_expired()
    _CHALLENGES[user_id] = {"code": code, "expires_at": time.time() + ttl_seconds}


def check_answer(user_id: int, answer: str) -> tuple[bool, str | None]:
    """
    Consumes the stored challenge (pass or fail) so each generated code is
    single-use - a fresh click of Verify is required to try again.
    Returns (passed, failure_reason). failure_reason is None on success.
    """
    entry = _CHALLENGES.pop(user_id, None)

    if entry is None:
        return False, "No active code found. Click Verify to get a new one."
    if time.time() > entry["expires_at"]:
        return False, "That code expired."
    if answer.strip().upper() == entry["code"]:
        return True, None
    return False, "That code didn't match."


def _cleanup_expired():
    now = time.time()
    expired = [uid for uid, entry in _CHALLENGES.items() if entry["expires_at"] < now]
    for uid in expired:
        _CHALLENGES.pop(uid, None)
