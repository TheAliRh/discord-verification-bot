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

Callers should rate-limit on TWO independent keys, not just one:
  1. Per (guild, user) - stops one Discord account from spamming Verify.
  2. Per destination (the actual email address / phone number) - stops
     many DIFFERENT Discord accounts, or accounts across many DIFFERENT
     guilds, from all sending codes to the same real inbox or phone number
     in a burst. Without this, per-user limiting alone doesn't protect a
     third party's inbox/phone from being bombarded, and doesn't protect
     the bot owner's SMTP/Twilio account from abuse-detection flags caused
     by many sends to one destination in a short window.

The destination cooldown is intentionally NOT read from any guild's own
settings. A guild's per-user cooldown_seconds is admin-configurable and
therefore untrusted for this purpose - a careless or malicious guild owner
could set their own cooldown to near-zero, and since the destination limit
exists specifically to protect people/systems OUTSIDE that guild's control,
it must not depend on that guild's configuration at all.
"""

import os
import time
import logging

logger = logging.getLogger(__name__)

_LAST_ACTION: dict[str, float] = (
    {}
)  # key -> timestamp of the last recorded (successful) action


def get_destination_cooldown_seconds() -> int:
    """
    Read fresh from the environment on every call (not cached at import
    time) - see core/email_sender.py's docstring for why module-level
    env-var caching is an import-order bug waiting to happen.
    """
    return int(os.getenv("DESTINATION_COOLDOWN_SECONDS", "60"))


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
