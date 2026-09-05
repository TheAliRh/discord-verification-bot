import time
from core.rate_limiter import check_and_record


def test_first_action_is_allowed():
    allowed, retry_after = check_and_record("email:1", cooldown_seconds=1)
    assert allowed is True
    assert retry_after == 0.0


def test_immediate_repeat_is_blocked():
    check_and_record("email:1", cooldown_seconds=1)
    allowed, retry_after = check_and_record("email:1", cooldown_seconds=1)
    assert allowed is False
    assert 0 < retry_after <= 1


def test_different_keys_are_independent():
    check_and_record("email:1", cooldown_seconds=1)
    allowed, _ = check_and_record("email:2", cooldown_seconds=1)
    assert allowed is True


def test_email_and_phone_namespaces_are_independent_for_same_user():
    check_and_record("email:1", cooldown_seconds=1)
    allowed, _ = check_and_record("phone:1", cooldown_seconds=1)
    assert allowed is True


def test_allowed_again_after_cooldown_elapses():
    check_and_record("email:1", cooldown_seconds=0.2)
    time.sleep(0.25)
    allowed, _ = check_and_record("email:1", cooldown_seconds=0.2)
    assert allowed is True
