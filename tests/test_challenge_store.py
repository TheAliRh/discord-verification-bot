import time
from core.challenge_store import (
    generate_code,
    store_challenge,
    check_answer,
    _SAFE_ALPHANUMERIC,
    _SAFE_NUMERIC,
)


def test_generate_code_respects_length_and_charset():
    for _ in range(100):
        code = generate_code(6, "alphanumeric")
        assert len(code) == 6
        assert all(c in _SAFE_ALPHANUMERIC for c in code)
        assert not any(c in code for c in "0O1I")  # ambiguous chars excluded


def test_generate_code_numeric_excludes_ambiguous_digits():
    for _ in range(100):
        code = generate_code(4, "numeric")
        assert len(code) == 4
        assert all(c in _SAFE_NUMERIC for c in code)
        assert "0" not in code and "1" not in code


def test_correct_answer_passes():
    store_challenge(user_id=1, code="ABC234")
    passed, reason = check_answer(1, "ABC234")
    assert passed is True
    assert reason is None


def test_answer_is_case_insensitive():
    store_challenge(user_id=1, code="ABC234")
    passed, _ = check_answer(1, "abc234")
    assert passed is True


def test_wrong_answer_fails_with_reason():
    store_challenge(user_id=1, code="ABC234")
    passed, reason = check_answer(1, "WRONGCODE")
    assert passed is False
    assert reason is not None


def test_challenge_is_single_use():
    store_challenge(user_id=1, code="ABC234")
    check_answer(1, "ABC234")  # first use consumes it
    passed, reason = check_answer(1, "ABC234")  # second attempt with same code
    assert passed is False
    assert reason is not None


def test_no_challenge_stored_fails_cleanly():
    passed, reason = check_answer(999, "ANYTHING")
    assert passed is False
    assert reason is not None


def test_expired_challenge_fails():
    store_challenge(user_id=1, code="ABC234", ttl_seconds=0)
    time.sleep(0.01)
    passed, reason = check_answer(1, "ABC234")
    assert passed is False
    assert "expired" in reason.lower()


def test_different_users_have_independent_challenges():
    store_challenge(user_id=1, code="AAA111")
    store_challenge(user_id=2, code="BBB222")

    passed1, _ = check_answer(1, "BBB222")  # user 1 guessing user 2's code
    assert passed1 is False

    passed2, _ = check_answer(2, "BBB222")
    assert passed2 is True
