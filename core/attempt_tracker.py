"""
Tracks failed verification attempts per (guild_id, user_id), independent of
any single challenge code.

A single code is already single-use - core/challenge_store.py consumes it
on the very first check, pass or fail. This module tracks something
different: how many times in a row a user has cycled through "click
Verify -> get a new code -> guess wrong". Without this, nothing stopped
unlimited retries - fail a code, click Verify again for a brand new one,
repeat forever. This is what actually enforces a guild's configured
max_attempts, locking the user out for cooldown_seconds once they hit it.
"""

import time

_ATTEMPTS: dict[tuple[int, int], dict[str, float]] = (
    {}
)  # (guild_id, user_id) -> {count, locked_until}


def _entry(guild_id: int, user_id: int) -> dict[str, float]:
    return _ATTEMPTS.setdefault(
        (guild_id, user_id), {"count": 0.0, "locked_until": 0.0}
    )


def record_failed_attempt(guild_id: int, user_id: int) -> int:
    """Increments and returns the new failed-attempt count for this user in this guild."""
    entry = _entry(guild_id, user_id)
    entry["count"] += 1
    return int(entry["count"])


def get_failed_attempts(guild_id: int, user_id: int) -> int:
    entry = _ATTEMPTS.get((guild_id, user_id))
    return int(entry["count"]) if entry else 0


def lock_out(guild_id: int, user_id: int, cooldown_seconds: int) -> None:
    """Called once max_attempts is reached - blocks new attempts until the cooldown elapses."""
    entry = _entry(guild_id, user_id)
    entry["locked_until"] = time.time() + cooldown_seconds


def is_locked_out(guild_id: int, user_id: int) -> tuple[bool, float]:
    """Returns (locked, seconds_remaining). Not locked out once the cooldown has elapsed."""
    entry = _ATTEMPTS.get((guild_id, user_id))
    if entry is None:
        return False, 0.0
    remaining = entry["locked_until"] - time.time()
    if remaining > 0:
        return True, remaining
    return False, 0.0


def reset_attempts(guild_id: int, user_id: int) -> None:
    """Call on successful verification - clears both the failure count and any lockout."""
    _ATTEMPTS.pop((guild_id, user_id), None)
