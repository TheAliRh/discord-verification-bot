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


def test_generate_code_uses_secrets_not_random():
    """
    Security-sensitive codes must come from a cryptographically secure
    source. Python's `random` module (Mersenne Twister) is predictable
    from past output and must never back an actual verification secret -
    only `secrets` (backed by os.urandom()) is acceptable here.
    """
    import secrets as secrets_module
    from unittest.mock import patch
    import core.challenge_store as challenge_store_module

    assert challenge_store_module.secrets is secrets_module

    with patch(
        "core.challenge_store.secrets.choice", wraps=secrets_module.choice
    ) as spy:
        code = generate_code(6, "alphanumeric")

    assert spy.call_count == 6  # one secrets.choice() call per character
    assert len(code) == 6


def test_correct_answer_passes():
    store_challenge(guild_id=100, user_id=1, method="captcha", code="ABC234")
    passed, reason = check_answer(100, 1, "captcha", "ABC234")
    assert passed is True
    assert reason is None


def test_answer_is_case_insensitive():
    store_challenge(guild_id=100, user_id=1, method="captcha", code="ABC234")
    passed, _ = check_answer(100, 1, "captcha", "abc234")
    assert passed is True


def test_wrong_answer_fails_with_reason():
    store_challenge(guild_id=100, user_id=1, method="captcha", code="ABC234")
    passed, reason = check_answer(100, 1, "captcha", "WRONGCODE")
    assert passed is False
    assert reason is not None


def test_challenge_is_single_use():
    store_challenge(guild_id=100, user_id=1, method="captcha", code="ABC234")
    check_answer(100, 1, "captcha", "ABC234")  # first use consumes it
    passed, reason = check_answer(
        100, 1, "captcha", "ABC234"
    )  # second attempt with same code
    assert passed is False
    assert reason is not None


def test_no_challenge_stored_fails_cleanly():
    passed, reason = check_answer(100, 999, "captcha", "ANYTHING")
    assert passed is False
    assert reason is not None


def test_expired_challenge_fails():
    store_challenge(
        guild_id=100, user_id=1, method="captcha", code="ABC234", ttl_seconds=0
    )
    time.sleep(0.01)
    passed, reason = check_answer(100, 1, "captcha", "ABC234")
    assert passed is False
    assert reason is not None
    assert "expired" in reason.lower()


def test_different_users_have_independent_challenges():
    store_challenge(guild_id=100, user_id=1, method="captcha", code="AAA111")
    store_challenge(guild_id=100, user_id=2, method="captcha", code="BBB222")

    passed1, _ = check_answer(
        100, 1, "captcha", "BBB222"
    )  # user 1 guessing user 2's code
    assert passed1 is False

    passed2, _ = check_answer(100, 2, "captcha", "BBB222")
    assert passed2 is True


# --- Same user, different guilds ---


def test_same_user_different_guilds_do_not_overwrite_each_other():
    """
    A user who is a member of two servers both running this bot could click
    Verify in Guild A, then click Verify in Guild B before finishing - these
    must be two independent challenges, not one overwriting the other.
    """
    store_challenge(guild_id=100, user_id=1, method="captcha", code="GUILDA1")
    store_challenge(
        guild_id=200, user_id=1, method="captcha", code="GUILDB1"
    )  # same user, different guild

    passed_a, _ = check_answer(100, 1, "captcha", "GUILDA1")
    assert passed_a is True

    passed_b, _ = check_answer(200, 1, "captcha", "GUILDB1")
    assert passed_b is True


def test_same_user_different_guilds_cannot_cross_submit_codes():
    """A code generated for Guild A must NOT be accepted when checked against Guild B."""
    store_challenge(guild_id=100, user_id=1, method="captcha", code="ONLYFORA")
    store_challenge(guild_id=200, user_id=1, method="captcha", code="ONLYFORB")

    passed, reason = check_answer(200, 1, "captcha", "ONLYFORA")
    assert passed is False
    assert reason is not None


def test_completing_one_guilds_challenge_does_not_consume_the_others():
    """Checking (and consuming) Guild A's challenge must leave Guild B's untouched."""
    store_challenge(guild_id=100, user_id=1, method="captcha", code="CODEA")
    store_challenge(guild_id=200, user_id=1, method="captcha", code="CODEB")

    check_answer(
        100, 1, "captcha", "CODEA"
    )  # completes and consumes Guild A's challenge only

    passed_b, _ = check_answer(200, 1, "captcha", "CODEB")
    assert passed_b is True


# --- The actual bug being fixed: same (guild, user), different methods ---


def test_same_guild_and_user_different_methods_do_not_overwrite_each_other():
    """
    A stale leftover message from a previously-configured method (persistent
    views keep old buttons working even after an admin switches methods)
    must not collide with a challenge from the CURRENTLY configured method.
    """
    store_challenge(guild_id=1, user_id=1, method="captcha", code="CAPTCHACODE")
    store_challenge(
        guild_id=1, user_id=1, method="email", code="EMAILCODE"
    )  # same guild+user, different method

    passed_captcha, _ = check_answer(1, 1, "captcha", "CAPTCHACODE")
    assert passed_captcha is True

    passed_email, _ = check_answer(1, 1, "email", "EMAILCODE")
    assert passed_email is True


def test_a_captcha_code_cannot_be_submitted_as_an_email_code():
    """
    The actual security gap: an instantly-visible captcha code must NOT be
    acceptable as proof of controlling an email inbox, even for the exact
    same (guild_id, user_id).
    """
    store_challenge(guild_id=1, user_id=1, method="captcha", code="VISIBLE1")
    store_challenge(guild_id=1, user_id=1, method="email", code="EMAILED1")

    # Try to "verify by email" using the captcha's code instead of the emailed one
    passed, reason = check_answer(1, 1, "email", "VISIBLE1")
    assert passed is False
    assert reason is not None


def test_a_phone_code_cannot_be_submitted_as_a_captcha_code():
    """Same gap, opposite direction, different method pair."""
    store_challenge(guild_id=1, user_id=1, method="phone", code="TEXTED99")
    store_challenge(guild_id=1, user_id=1, method="captcha", code="SHOWN123")

    passed, reason = check_answer(1, 1, "captcha", "TEXTED99")
    assert passed is False
    assert reason is not None


def test_completing_one_methods_challenge_does_not_consume_a_different_methods():
    """Checking (and consuming) the captcha challenge must leave the email challenge untouched."""
    store_challenge(guild_id=1, user_id=1, method="captcha", code="CAPCODE")
    store_challenge(guild_id=1, user_id=1, method="email", code="MAILCODE")

    check_answer(1, 1, "captcha", "CAPCODE")  # consumes only the captcha challenge

    passed_email, _ = check_answer(1, 1, "email", "MAILCODE")
    assert passed_email is True  # unaffected by the captcha check above
