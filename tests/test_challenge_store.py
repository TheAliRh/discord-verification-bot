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
    store_challenge(guild_id=100, user_id=1, code="ABC234")
    passed, reason = check_answer(100, 1, "ABC234")
    assert passed is True
    assert reason is None


def test_answer_is_case_insensitive():
    store_challenge(guild_id=100, user_id=1, code="ABC234")
    passed, _ = check_answer(100, 1, "abc234")
    assert passed is True


def test_wrong_answer_fails_with_reason():
    store_challenge(guild_id=100, user_id=1, code="ABC234")
    passed, reason = check_answer(100, 1, "WRONGCODE")
    assert passed is False
    assert reason is not None


def test_challenge_is_single_use():
    store_challenge(guild_id=100, user_id=1, code="ABC234")
    check_answer(100, 1, "ABC234")  # first use consumes it
    passed, reason = check_answer(100, 1, "ABC234")  # second attempt with same code
    assert passed is False
    assert reason is not None


def test_no_challenge_stored_fails_cleanly():
    passed, reason = check_answer(100, 999, "ANYTHING")
    assert passed is False
    assert reason is not None


def test_expired_challenge_fails():
    store_challenge(guild_id=100, user_id=1, code="ABC234", ttl_seconds=0)
    time.sleep(0.01)
    passed, reason = check_answer(100, 1, "ABC234")
    assert passed is False
    assert reason is not None
    assert "expired" in reason.lower()


def test_different_users_have_independent_challenges():
    store_challenge(guild_id=100, user_id=1, code="AAA111")
    store_challenge(guild_id=100, user_id=2, code="BBB222")

    passed1, _ = check_answer(100, 1, "BBB222")  # user 1 guessing user 2's code
    assert passed1 is False

    passed2, _ = check_answer(100, 2, "BBB222")
    assert passed2 is True


# --- The actual bug being fixed: same user, different guilds ---


def test_same_user_different_guilds_do_not_overwrite_each_other():
    """
    A user who is a member of two servers both running this bot could click
    Verify in Guild A, then click Verify in Guild B before finishing - these
    must be two independent challenges, not one overwriting the other.
    """
    store_challenge(guild_id=100, user_id=1, code="GUILDA1")
    store_challenge(
        guild_id=200, user_id=1, code="GUILDB1"
    )  # same user, different guild

    # Guild A's code must still work, unaffected by Guild B's challenge existing
    passed_a, _ = check_answer(100, 1, "GUILDA1")
    assert passed_a is True

    # Guild B's code must still work independently too
    passed_b, _ = check_answer(200, 1, "GUILDB1")
    assert passed_b is True


def test_same_user_different_guilds_cannot_cross_submit_codes():
    """A code generated for Guild A must NOT be accepted when checked against Guild B."""
    store_challenge(guild_id=100, user_id=1, code="ONLYFORA")
    store_challenge(guild_id=200, user_id=1, code="ONLYFORB")

    # Submitting Guild A's code while "in" Guild B's challenge context must fail
    passed, reason = check_answer(200, 1, "ONLYFORA")
    assert passed is False
    assert reason is not None


def test_completing_one_guilds_challenge_does_not_consume_the_others():
    """Checking (and consuming) Guild A's challenge must leave Guild B's untouched."""
    store_challenge(guild_id=100, user_id=1, code="CODEA")
    store_challenge(guild_id=200, user_id=1, code="CODEB")

    check_answer(100, 1, "CODEA")  # completes and consumes Guild A's challenge only

    # Guild B's challenge must still be there, unaffected
    passed_b, _ = check_answer(200, 1, "CODEB")
    assert passed_b is True
