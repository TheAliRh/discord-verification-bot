import time
from core.rate_limiter import is_allowed, record, get_destination_cooldown_seconds


def test_first_check_is_allowed():
    allowed, retry_after = is_allowed("email:1", cooldown_seconds=1)
    assert allowed is True
    assert retry_after == 0.0


def test_checking_alone_does_not_record():
    """is_allowed() must be side-effect-free - calling it repeatedly must not itself start a cooldown."""
    is_allowed("email:1", cooldown_seconds=1)
    is_allowed("email:1", cooldown_seconds=1)
    allowed, retry_after = is_allowed("email:1", cooldown_seconds=1)
    assert allowed is True
    assert retry_after == 0.0


def test_recorded_action_blocks_immediate_repeat():
    record("email:1")
    allowed, retry_after = is_allowed("email:1", cooldown_seconds=1)
    assert allowed is False
    assert 0 < retry_after <= 1


def test_different_keys_are_independent():
    record("email:1")
    allowed, _ = is_allowed("email:2", cooldown_seconds=1)
    assert allowed is True


def test_email_and_phone_namespaces_are_independent_for_same_user():
    record("email:1")
    allowed, _ = is_allowed("phone:1", cooldown_seconds=1)
    assert allowed is True


def test_allowed_again_after_cooldown_elapses():
    record("email:1")
    time.sleep(0.05)
    allowed, _ = is_allowed("email:1", cooldown_seconds=0.03)
    assert allowed is True


# --- The actual bug being fixed: a failed send must not burn the cooldown ---


def test_failed_action_does_not_start_a_cooldown():
    """
    Simulates the real bug: check the rate limit, attempt to send, the send
    fails, so record() is never called. A subsequent attempt must be allowed
    immediately - the user should never be locked out for a message that
    was never actually sent.
    """
    allowed_first, _ = is_allowed("email:1", cooldown_seconds=60)
    assert allowed_first is True

    # ... the send fails here, so the caller does NOT call record() ...

    allowed_retry, retry_after = is_allowed("email:1", cooldown_seconds=60)
    assert allowed_retry is True  # not falsely rate-limited by the failed attempt
    assert retry_after == 0.0


def test_successful_action_does_start_a_cooldown():
    """The mirror case: once record() IS called (send succeeded), the cooldown applies."""
    allowed_first, _ = is_allowed("email:1", cooldown_seconds=60)
    assert allowed_first is True

    record("email:1")  # the send succeeded

    allowed_retry, retry_after = is_allowed("email:1", cooldown_seconds=60)
    assert allowed_retry is False
    assert 0 < retry_after <= 60


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
