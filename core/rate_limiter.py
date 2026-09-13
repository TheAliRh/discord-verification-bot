"""
Simple in-memory per-user rate limiter.

Separate from core/challenge_store.py: that module limits how many times a
CODE can be guessed. This module limits how often an external, costly
ACTION (sending an email or SMS) can be triggered in the first place -
without it, spam-clicking Verify on email/phone methods sends unlimited
messages at your SMTP/Twilio account's expense.

try_acquire() checks AND reserves the slot in one synchronous step, with no
`await` inside it. This matters: asyncio only switches between coroutines
at `await` points, so a plain synchronous function can never be interleaved
by another coroutine's call to the same function. If checking and recording
were two separate calls with the actual network send awaited in between (as
an earlier version of this module did), two near-simultaneous requests for
the same key could both see "allowed" before either one had recorded
anything - letting both through. Combining them into one atomic step closes
that window entirely.

Because try_acquire() reserves the slot immediately, on the assumption the
guarded action will succeed, callers must call release() if that action
actually fails (e.g. the email/SMS send raised an exception). Without this,
a failed send would still cost the user their cooldown window for a
message they never received - the same problem the atomicity fix must not
reintroduce.

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
)  # key -> timestamp of the last acquired (reserved) action


def get_destination_cooldown_seconds() -> int:
    """
    Read fresh from the environment on every call (not cached at import
    time) - see core/email_sender.py's docstring for why module-level
    env-var caching is an import-order bug waiting to happen.
    """
    return int(os.getenv("DESTINATION_COOLDOWN_SECONDS", "60"))


def try_acquire(key: str, cooldown_seconds: int) -> tuple[bool, float]:
    """
    Atomically checks the cooldown AND, if allowed, immediately reserves it -
    a single synchronous operation with no `await` inside it, so two
    concurrent callers can never both observe "allowed" for the same key.

    Returns (acquired, retry_after_seconds). If acquired is False, nothing
    was reserved - retry_after_seconds says how long until it's clear.

    If acquired is True but the action this reservation guards subsequently
    fails, call release(key) to undo it rather than leaving the user
    penalized for something that never actually happened.
    """
    now = time.time()
    last = _LAST_ACTION.get(key)

    if last is not None:
        elapsed = now - last
        if elapsed < cooldown_seconds:
            retry_after = cooldown_seconds - elapsed
            logger.info("Rate limit hit for '%s' - %.1fs remaining", key, retry_after)
            return False, retry_after

    # Reserve immediately - no `await` between the check above and this
    # write, so this whole function is atomic with respect to other
    # coroutines regardless of how many are waiting to run.
    _LAST_ACTION[key] = now
    return True, 0.0


def release(key: str) -> None:
    """
    Undo a reservation made by try_acquire(), because the action it was
    guarding failed. Without this, a failed send would still cost the user
    their cooldown window for a message they never actually received.
    """
    _LAST_ACTION.pop(key, None)
