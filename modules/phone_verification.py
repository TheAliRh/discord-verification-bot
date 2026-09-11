"""
Phone (SMS) verification.

Flow:
  1. User clicks Verify (after passing shared pre-checks) -> modal asks for
     their phone number in E.164 format (e.g. +14155551234).
  2. We generate a code (same shared challenge_store as every captcha-style
     module), send it via Twilio SMS, and show an "Enter Code" button.
  3. Clicking that opens a second modal for the code -> checked the same way
     every other module checks it.

Requires TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER in
.env, plus a paid Twilio account with a number able to send SMS to the
destination country. If unset, users get a clear "not available" message
instead of a silent failure.
"""

import re
import logging
from typing import Any

import discord
from core.base import VerificationModule
from core import service
from core.prechecks import passes_prechecks
from core.challenge_store import generate_code, store_challenge, check_answer
from core.rate_limiter import is_allowed, record, get_destination_cooldown_seconds
from core.sms_sender import send_verification_sms, SMSNotConfigured, SMSSendError
from core.ui_base import BaseView, BaseModal

logger = logging.getLogger(__name__)

# E.164 format: + followed by 8-15 digits, no spaces/dashes/parens.
# Deliberately strict - Twilio rejects malformed numbers anyway, but this
# catches obvious mistakes before we spend an API call on them.
_E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def _looks_like_phone_number(number: str) -> bool:
    return bool(_E164_PATTERN.match(number.strip()))


class EnterPhoneCodeModal(BaseModal, title="Enter the code we texted you"):
    answer: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="Code", placeholder="e.g. AB3XZ9", max_length=10
    )

    def __init__(self, settings: dict[str, Any]):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            return  # this modal is only ever opened from a button inside a guild

        passed, reason = check_answer(
            interaction.guild_id, interaction.user.id, "phone", self.answer.value
        )
        if passed:
            await service.grant_verified(interaction, self.settings)
        else:
            await service.deny_verified(
                interaction, self.settings, reason or "Incorrect answer."
            )


class EnterPhoneCodeButton(discord.ui.Button[Any]):
    def __init__(self, settings: dict[str, Any]):
        super().__init__(label="Enter Code", style=discord.ButtonStyle.primary)
        self.settings = settings

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(EnterPhoneCodeModal(self.settings))


class EnterPhoneCodeView(BaseView):
    def __init__(self, settings: dict[str, Any]):
        super().__init__(timeout=300)
        self.add_item(EnterPhoneCodeButton(settings))


class PhoneNumberModal(BaseModal, title="Verify by Phone"):
    phone_number: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="Your phone number (with country code)",
        placeholder="+14155551234",
    )

    def __init__(self, settings: dict[str, Any]):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return  # this modal is only ever opened from a button inside a guild

        # Defer immediately, before anything else. Discord requires an
        # initial response within 3 seconds - sending the actual SMS is an
        # external network call (Twilio) that can easily take longer than
        # that. Deferring extends the effective response window to ~15
        # minutes and switches every subsequent reply to
        # interaction.followup.send() instead of interaction.response.send_message().
        await interaction.response.defer(ephemeral=True)

        number = self.phone_number.value.strip()

        if not _looks_like_phone_number(number):
            await interaction.followup.send(
                "That doesn't look like a valid phone number. Include the country code, "
                "e.g. `+14155551234`. Click Verify to try again.",
                ephemeral=True,
            )
            return

        method_settings = self.settings["method_settings"].get("phone", {})
        rate_limit_key = f"phone:{interaction.guild.id}:{interaction.user.id}"
        cooldown_seconds = method_settings.get("cooldown_seconds", 60)

        allowed, retry_after = is_allowed(rate_limit_key, cooldown_seconds)
        if not allowed:
            await interaction.followup.send(
                f"Please wait {int(retry_after) + 1} more second(s) before requesting another code.",
                ephemeral=True,
            )
            return

        # Destination-scoped limit: global (no guild_id), and NOT using this
        # guild's own cooldown_seconds - see core/rate_limiter.py's docstring
        # for why. This is what actually stops many different Discord
        # accounts (or accounts in different guilds) from all texting codes
        # to the same real phone number in a burst.
        destination_key = f"phone_dest:{number}"
        destination_allowed, destination_retry_after = is_allowed(
            destination_key, get_destination_cooldown_seconds()
        )
        if not destination_allowed:
            await interaction.followup.send(
                "That phone number was used very recently for another verification attempt. "
                f"Please wait {int(destination_retry_after) + 1} more second(s), or use a different number.",
                ephemeral=True,
            )
            return

        code = generate_code(method_settings.get("length", 6), "numeric")

        try:
            await send_verification_sms(number, code, interaction.guild.name)
        except SMSNotConfigured:
            logger.warning(
                "Phone verification attempted but Twilio is not configured (guild %s)",
                interaction.guild_id,
            )
            await interaction.followup.send(
                "Phone verification isn't fully set up on this server's bot yet. "
                "Ask an admin to configure Twilio, or try a different verification method.",
                ephemeral=True,
            )
            return
        except SMSSendError:
            logger.warning(
                "Twilio rejected an SMS send for user %s in guild %s",
                interaction.user.id,
                interaction.guild_id,
            )
            await interaction.followup.send(
                "Couldn't send a text to that number. Double-check it's correct, "
                "or try a different verification method.",
                ephemeral=True,
            )
            return
        except Exception:
            logger.exception(
                "Unexpected error sending verification SMS in guild %s",
                interaction.guild_id,
            )
            await interaction.followup.send(
                "Something went wrong sending the code. Please try again in a moment.",
                ephemeral=True,
            )
            return

        # Only store the challenge and record the rate limit now that the SMS
        # was actually sent - doing this beforehand would leave a valid,
        # checkable code sitting active for a message the user never received.
        store_challenge(interaction.guild.id, interaction.user.id, "phone", code)
        record(rate_limit_key)
        record(destination_key)
        logger.info(
            "Sent verification SMS for user %s in guild %s",
            interaction.user.id,
            interaction.guild_id,
        )

        await interaction.followup.send(
            f"Sent a code to {number}. Click below once you have it.",
            view=EnterPhoneCodeView(self.settings),
            ephemeral=True,
        )


class PhoneVerifyButton(discord.ui.Button[Any]):
    def __init__(self) -> None:
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="📱",
            custom_id="verify:phone:click",
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id is None:
            return  # this button only ever appears on a message inside a guild

        from settings import settings_manager

        guild_settings = await settings_manager.get(interaction.guild_id)

        if not await passes_prechecks(interaction, guild_settings):
            return

        await interaction.response.send_modal(PhoneNumberModal(guild_settings))


class PhoneVerificationView(BaseView):
    def __init__(self) -> None:
        super().__init__(timeout=None)  # persists across restarts
        self.add_item(PhoneVerifyButton())


class PhoneVerification(VerificationModule):
    key = "phone"
    display_name = "Phone (SMS)"

    def build_entry_view(self, settings: dict[str, Any]) -> discord.ui.View:
        return PhoneVerificationView()
