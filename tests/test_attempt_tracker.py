import time
from core.attempt_tracker import (
    record_failed_attempt,
    get_failed_attempts,
    lock_out,
    is_locked_out,
    reset_attempts,
)


def test_first_failure_is_recorded():
    count = record_failed_attempt(guild_id=1, user_id=1)
    assert count == 1
    assert get_failed_attempts(1, 1) == 1


def test_failures_accumulate():
    record_failed_attempt(1, 1)
    record_failed_attempt(1, 1)
    count = record_failed_attempt(1, 1)
    assert count == 3
    assert get_failed_attempts(1, 1) == 3


def test_different_guilds_track_independently_for_same_user():
    record_failed_attempt(guild_id=100, user_id=1)
    record_failed_attempt(guild_id=100, user_id=1)
    record_failed_attempt(guild_id=200, user_id=1)

    assert get_failed_attempts(100, 1) == 2
    assert get_failed_attempts(200, 1) == 1


def test_not_locked_out_by_default():
    locked, remaining = is_locked_out(999, 999)
    assert locked is False
    assert remaining == 0.0


def test_lock_out_makes_user_locked():
    lock_out(guild_id=1, user_id=1, cooldown_seconds=60)
    locked, remaining = is_locked_out(1, 1)
    assert locked is True
    assert 0 < remaining <= 60


def test_lock_out_expires_after_cooldown():
    lock_out(guild_id=1, user_id=1, cooldown_seconds=0.1)
    time.sleep(0.15)
    locked, remaining = is_locked_out(1, 1)
    assert locked is False
    assert remaining == 0.0


def test_reset_clears_both_count_and_lockout():
    record_failed_attempt(1, 1)
    record_failed_attempt(1, 1)
    lock_out(1, 1, cooldown_seconds=60)

    reset_attempts(1, 1)

    assert get_failed_attempts(1, 1) == 0
    locked, _ = is_locked_out(1, 1)
    assert locked is False
