"""
Simple in-memory per-user rate limiter.

Separate from core/challenge_store.py: that module limits how many times a
CODE can be guessed. This module limits how often an external, costly
ACTION (sending an email or SMS) can be triggered in the first place -
without it, spam-clicking Verify on email/phone methods sends unlimited
messages at your SMTP/Twilio account's expense.
"""

import time
import logging

logger = logging.getLogger(__name__)

_LAST_ACTION: dict[str, float] = {}  # key -> timestamp of the last allowed action


def check_and_record(key: str, cooldown_seconds: int) -> tuple[bool, float]:
    """
    Returns (allowed, retry_after_seconds).

    If allowed is True, the action is recorded as having just happened -
    the next call with the same key will be blocked until cooldown_seconds
    have passed. If allowed is False, retry_after_seconds says how much
    longer the caller needs to wait.
    """
    now = time.time()
    last = _LAST_ACTION.get(key)

    if last is not None:
        elapsed = now - last
        if elapsed < cooldown_seconds:
            retry_after = cooldown_seconds - elapsed
            logger.info("Rate limit hit for '%s' - %.1fs remaining", key, retry_after)
            return False, retry_after

    _LAST_ACTION[key] = now
    return True, 0.0
