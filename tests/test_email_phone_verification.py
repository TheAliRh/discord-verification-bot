from unittest.mock import AsyncMock, patch

import modules.email_verification as email_mod
import modules.phone_verification as phone_mod
from tests.conftest import FakeInteraction, FakeMember


# --- Email address validation ---


def test_valid_email_addresses_accepted():
    for addr in ["user@example.com", "a.b@sub.domain.co"]:
        assert email_mod._looks_like_email(addr) is True


def test_invalid_email_addresses_rejected():
    for addr in [
        "not-an-email",
        "user@",
        "@example.com",
        "user @example.com",
        "user@example",
        "user@@example.com",
    ]:
        assert email_mod._looks_like_email(addr) is False


# --- Phone number validation (E.164) ---


def test_valid_phone_numbers_accepted():
    for num in ["+14155551234", "+442071838750", "+912212345678"]:
        assert phone_mod._looks_like_phone_number(num) is True


def test_invalid_phone_numbers_rejected():
    for num in [
        "14155551234",
        "+1 415 555 1234",
        "+0123456789",
        "not-a-number",
        "+1",
        "415-555-1234",
    ]:
        assert phone_mod._looks_like_phone_number(num) is False


# --- Rate limiting wired into the actual send flow ---


async def test_email_second_submission_is_rate_limited_and_not_resent():
    settings = {"method_settings": {"email": {"length": 6, "cooldown_seconds": 60}}}
    send_mock = AsyncMock()

    with patch.object(email_mod, "send_verification_email", send_mock):
        modal1 = email_mod.EmailAddressModal(settings)
        modal1.email._value = "user@example.com"
        interaction1 = FakeInteraction(user=FakeMember(user_id=42))
        await modal1.on_submit(interaction1)

        modal2 = email_mod.EmailAddressModal(settings)
        modal2.email._value = "user@example.com"
        interaction2 = FakeInteraction(user=FakeMember(user_id=42))
        await modal2.on_submit(interaction2)

    assert send_mock.call_count == 1  # second attempt did not send
    assert "wait" in interaction2.response.sent[0].lower()


async def test_email_different_users_are_not_rate_limited_by_each_other():
    settings = {"method_settings": {"email": {"length": 6, "cooldown_seconds": 60}}}
    send_mock = AsyncMock()

    with patch.object(email_mod, "send_verification_email", send_mock):
        modal1 = email_mod.EmailAddressModal(settings)
        modal1.email._value = "user@example.com"
        await modal1.on_submit(FakeInteraction(user=FakeMember(user_id=1)))

        modal2 = email_mod.EmailAddressModal(settings)
        modal2.email._value = "other@example.com"
        await modal2.on_submit(FakeInteraction(user=FakeMember(user_id=2)))

    assert send_mock.call_count == 2


async def test_phone_second_submission_is_rate_limited_and_not_resent():
    settings = {"method_settings": {"phone": {"length": 6, "cooldown_seconds": 60}}}
    send_mock = AsyncMock()

    with patch.object(phone_mod, "send_verification_sms", send_mock):
        modal1 = phone_mod.PhoneNumberModal(settings)
        modal1.phone_number._value = "+14155551234"
        interaction1 = FakeInteraction(user=FakeMember(user_id=55))
        await modal1.on_submit(interaction1)

        modal2 = phone_mod.PhoneNumberModal(settings)
        modal2.phone_number._value = "+14155551234"
        interaction2 = FakeInteraction(user=FakeMember(user_id=55))
        await modal2.on_submit(interaction2)

    assert send_mock.call_count == 1
    assert "wait" in interaction2.response.sent[0].lower()


async def test_email_not_configured_gives_clear_message():
    settings = {"method_settings": {"email": {"length": 6, "cooldown_seconds": 60}}}

    with patch.object(
        email_mod,
        "send_verification_email",
        AsyncMock(side_effect=email_mod.EmailNotConfigured()),
    ):
        modal = email_mod.EmailAddressModal(settings)
        modal.email._value = "user@example.com"
        interaction = FakeInteraction(user=FakeMember(user_id=1))
        await modal.on_submit(interaction)

    assert "isn't fully set up" in interaction.response.sent[0]


# --- The actual bug being fixed: a failed send must not burn the cooldown ---


async def test_email_failed_send_does_not_rate_limit_immediate_retry():
    """
    Regression test: previously the rate limit was recorded BEFORE attempting
    the send, so a failure (SMTP down, misconfigured, etc.) would still lock
    the user out for the full cooldown even though no email was ever sent.
    """
    settings = {"method_settings": {"email": {"length": 6, "cooldown_seconds": 60}}}
    same_user = FakeMember(user_id=42)

    failing_send = AsyncMock(side_effect=RuntimeError("simulated SMTP failure"))
    with patch.object(email_mod, "send_verification_email", failing_send):
        modal1 = email_mod.EmailAddressModal(settings)
        modal1.email._value = "user@example.com"
        interaction1 = FakeInteraction(user=same_user)
        await modal1.on_submit(interaction1)

    assert "went wrong" in interaction1.response.sent[0].lower()

    # Immediately retry - must NOT be rate-limited, since nothing was actually sent
    working_send = AsyncMock()
    with patch.object(email_mod, "send_verification_email", working_send):
        modal2 = email_mod.EmailAddressModal(settings)
        modal2.email._value = "user@example.com"
        interaction2 = FakeInteraction(user=same_user)
        await modal2.on_submit(interaction2)

    assert working_send.call_count == 1  # the retry actually attempted to send
    assert "wait" not in interaction2.response.sent[0].lower()
    assert "Sent a code" in interaction2.response.sent[0]


async def test_email_not_configured_does_not_rate_limit_retry():
    settings = {"method_settings": {"email": {"length": 6, "cooldown_seconds": 60}}}
    same_user = FakeMember(user_id=43)

    with patch.object(
        email_mod,
        "send_verification_email",
        AsyncMock(side_effect=email_mod.EmailNotConfigured()),
    ):
        modal1 = email_mod.EmailAddressModal(settings)
        modal1.email._value = "user@example.com"
        await modal1.on_submit(FakeInteraction(user=same_user))

    working_send = AsyncMock()
    with patch.object(email_mod, "send_verification_email", working_send):
        modal2 = email_mod.EmailAddressModal(settings)
        modal2.email._value = "user@example.com"
        interaction2 = FakeInteraction(user=same_user)
        await modal2.on_submit(interaction2)

    assert working_send.call_count == 1
    assert "wait" not in interaction2.response.sent[0].lower()


async def test_phone_failed_send_does_not_rate_limit_immediate_retry():
    settings = {"method_settings": {"phone": {"length": 6, "cooldown_seconds": 60}}}
    same_user = FakeMember(user_id=77)

    failing_send = AsyncMock(
        side_effect=phone_mod.SMSSendError("Twilio rejected the number")
    )
    with patch.object(phone_mod, "send_verification_sms", failing_send):
        modal1 = phone_mod.PhoneNumberModal(settings)
        modal1.phone_number._value = "+14155551234"
        interaction1 = FakeInteraction(user=same_user)
        await modal1.on_submit(interaction1)

    assert "couldn't send" in interaction1.response.sent[0].lower()

    working_send = AsyncMock()
    with patch.object(phone_mod, "send_verification_sms", working_send):
        modal2 = phone_mod.PhoneNumberModal(settings)
        modal2.phone_number._value = "+14155551234"
        interaction2 = FakeInteraction(user=same_user)
        await modal2.on_submit(interaction2)

    assert working_send.call_count == 1  # the retry actually attempted to send
    assert "wait" not in interaction2.response.sent[0].lower()
    assert "Sent a code" in interaction2.response.sent[0]


async def test_email_successful_send_still_enforces_the_cooldown():
    """The mirror case: a send that DOES succeed must still rate-limit the next attempt."""
    settings = {"method_settings": {"email": {"length": 6, "cooldown_seconds": 60}}}
    same_user = FakeMember(user_id=99)

    send_mock = AsyncMock()
    with patch.object(email_mod, "send_verification_email", send_mock):
        modal1 = email_mod.EmailAddressModal(settings)
        modal1.email._value = "user@example.com"
        await modal1.on_submit(FakeInteraction(user=same_user))

        modal2 = email_mod.EmailAddressModal(settings)
        modal2.email._value = "user@example.com"
        interaction2 = FakeInteraction(user=same_user)
        await modal2.on_submit(interaction2)

    assert send_mock.call_count == 1  # second attempt correctly blocked
    assert "wait" in interaction2.response.sent[0].lower()
