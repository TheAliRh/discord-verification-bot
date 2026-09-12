import asyncio
import time
from core.rate_limiter import try_acquire, release, get_destination_cooldown_seconds


def test_first_check_is_acquired():
    acquired, retry_after = try_acquire("email:1", cooldown_seconds=1)
    assert acquired is True
    assert retry_after == 0.0


def test_acquiring_reserves_immediately_blocking_the_next_check():
    """Unlike the old split API, a single try_acquire() call both checks AND reserves."""
    try_acquire("email:1", cooldown_seconds=1)
    acquired, retry_after = try_acquire("email:1", cooldown_seconds=1)
    assert acquired is False
    assert 0 < retry_after <= 1


def test_different_keys_are_independent():
    try_acquire("email:1", cooldown_seconds=1)
    acquired, _ = try_acquire("email:2", cooldown_seconds=1)
    assert acquired is True


def test_email_and_phone_namespaces_are_independent_for_same_user():
    try_acquire("email:1", cooldown_seconds=1)
    acquired, _ = try_acquire("phone:1", cooldown_seconds=1)
    assert acquired is True


def test_allowed_again_after_cooldown_elapses():
    try_acquire("email:1", cooldown_seconds=0.03)
    time.sleep(0.05)
    acquired, _ = try_acquire("email:1", cooldown_seconds=0.03)
    assert acquired is True


# --- release(): undoing a reservation when the guarded action fails ---


def test_release_allows_immediate_retry():
    """
    Simulates the real flow: acquire the slot, the guarded action fails, so
    the caller releases it - a subsequent attempt must be allowed
    immediately, not blocked by the reservation that was just undone.
    """
    acquired, _ = try_acquire("email:1", cooldown_seconds=60)
    assert acquired is True

    release("email:1")  # the send failed

    acquired_retry, retry_after = try_acquire("email:1", cooldown_seconds=60)
    assert acquired_retry is True
    assert retry_after == 0.0


def test_without_release_the_cooldown_still_applies():
    """The mirror case: if release() is NOT called (the action succeeded), the cooldown holds."""
    try_acquire("email:1", cooldown_seconds=60)
    acquired, retry_after = try_acquire("email:1", cooldown_seconds=60)
    assert acquired is False
    assert 0 < retry_after <= 60


def test_releasing_a_key_that_was_never_acquired_does_not_raise():
    release("never-acquired-key")  # must be a safe no-op


# --- Destination cooldown: read lazily from the environment, sane default ---


def test_destination_cooldown_defaults_to_60(monkeypatch):
    monkeypatch.delenv("DESTINATION_COOLDOWN_SECONDS", raising=False)
    assert get_destination_cooldown_seconds() == 60


def test_destination_cooldown_respects_env_var(monkeypatch):
    monkeypatch.setenv("DESTINATION_COOLDOWN_SECONDS", "120")
    assert get_destination_cooldown_seconds() == 120


def test_destination_cooldown_read_fresh_each_call(monkeypatch):
    """Must not be cached at import time - changing the env var must take effect immediately."""
    monkeypatch.setenv("DESTINATION_COOLDOWN_SECONDS", "30")
    assert get_destination_cooldown_seconds() == 30

    monkeypatch.setenv("DESTINATION_COOLDOWN_SECONDS", "90")
    assert get_destination_cooldown_seconds() == 90


# --- The actual bug being fixed: no race window between checking and reserving ---


async def test_two_concurrent_requests_for_the_same_key_only_one_succeeds():
    """
    The exact race condition being closed: two "simultaneous" requests for
    the same key, each awaiting something before checking the limit, must
    still result in exactly ONE of them acquiring the slot - never both.
    With the old split is_allowed()+record() API, both could see "allowed"
    if they checked before either had recorded anything.
    """
    results = []

    async def attempt():
        await asyncio.sleep(
            0
        )  # yield control once, so both tasks are genuinely interleaved
        acquired, _ = try_acquire("shared-key", cooldown_seconds=60)
        results.append(acquired)

    await asyncio.gather(attempt(), attempt())

    assert results.count(True) == 1
    assert results.count(False) == 1


async def test_many_concurrent_requests_for_the_same_key_only_one_succeeds():
    """Same test, scaled up - 20 concurrent attempts, still exactly one winner."""
    results = []

    async def attempt():
        await asyncio.sleep(0)
        acquired, _ = try_acquire("shared-key-2", cooldown_seconds=60)
        results.append(acquired)

    await asyncio.gather(*[attempt() for _ in range(20)])

    assert results.count(True) == 1
    assert results.count(False) == 19


async def test_concurrent_requests_for_different_keys_can_all_succeed():
    """Sanity check: the atomicity fix must not accidentally serialize unrelated keys."""
    results = []

    async def attempt(key):
        await asyncio.sleep(0)
        acquired, _ = try_acquire(key, cooldown_seconds=60)
        results.append(acquired)

    await asyncio.gather(*[attempt(f"independent-key-{i}") for i in range(10)])

    assert all(results)  # every distinct key should succeed independently
