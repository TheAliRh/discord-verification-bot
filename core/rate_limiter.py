"""
Simple in-memory per-user rate limiter.

Separate from core/challenge_store.py: that module limits how many times a
CODE can be guessed. This module limits how often an external, costly
ACTION (sending an email or SMS) can be triggered in the first place -
without it, spam-clicking Verify on email/phone methods sends unlimited
messages at your SMTP/Twilio account's expense.

Checking and recording are two separate steps - is_allowed() then record() -
not one atomic call, on purpose. The caller must check BEFORE attempting
the costly action, but should only record it AFTER that action actually
succeeds. Recording unconditionally before attempting the send burns the
user's cooldown even when nothing was actually sent - e.g. SMTP being
unconfigured, a transient network error, or Twilio rejecting the number
would all lock a legitimate user out for the full cooldown period for a
message they never received.
"""

import time
import logging

logger = logging.getLogger(__name__)

_LAST_ACTION: dict[str, float] = (
    {}
)  # key -> timestamp of the last recorded (successful) action


def is_allowed(key: str, cooldown_seconds: int) -> tuple[bool, float]:
    """
    Returns (allowed, retry_after_seconds) WITHOUT recording anything.
    Call record() yourself once the action you're gating actually succeeds -
    if it fails, simply don't call record(), and the user isn't penalized
    for a send that never happened.
    """
    now = time.time()
    last = _LAST_ACTION.get(key)

    if last is not None:
        elapsed = now - last
        if elapsed < cooldown_seconds:
            retry_after = cooldown_seconds - elapsed
            logger.info("Rate limit hit for '%s' - %.1fs remaining", key, retry_after)
            return False, retry_after

    return True, 0.0


def record(key: str) -> None:
    """Call only after the rate-limited action actually succeeded."""
    _LAST_ACTION[key] = time.time()
