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
import discord
from core.base import VerificationModule
from core import service
from core.prechecks import passes_prechecks
from core.challenge_store import generate_code, store_challenge, check_answer
from core.sms_sender import send_verification_sms, SMSNotConfigured, SMSSendError

# E.164 format: + followed by 8-15 digits, no spaces/dashes/parens.
# Deliberately strict - Twilio rejects malformed numbers anyway, but this
# catches obvious mistakes before we spend an API call on them.
_E164_PATTERN = re.compile(r"^\+[1-9]\d{7,14}$")


def _looks_like_phone_number(number: str) -> bool:
    return bool(_E164_PATTERN.match(number.strip()))


class EnterPhoneCodeModal(discord.ui.Modal, title="Enter the code we texted you"):
    answer = discord.ui.TextInput(
        label="Code", placeholder="e.g. AB3XZ9", max_length=10
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction):
        passed, reason = check_answer(interaction.user.id, self.answer.value)
        if passed:
            await service.grant_verified(interaction, self.settings)
        else:
            await service.deny_verified(interaction, self.settings, reason)


class EnterPhoneCodeButton(discord.ui.Button):
    def __init__(self, settings: dict):
        super().__init__(label="Enter Code", style=discord.ButtonStyle.primary)
        self.settings = settings

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EnterPhoneCodeModal(self.settings))


class EnterPhoneCodeView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=300)
        self.add_item(EnterPhoneCodeButton(settings))


class PhoneNumberModal(discord.ui.Modal, title="Verify by Phone"):
    phone_number = discord.ui.TextInput(
        label="Your phone number (with country code)",
        placeholder="+14155551234",
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction):
        number = self.phone_number.value.strip()

        if not _looks_like_phone_number(number):
            await interaction.response.send_message(
                "That doesn't look like a valid phone number. Include the country code, "
                "e.g. `+14155551234`. Click Verify to try again.",
                ephemeral=True,
            )
            return

        method_settings = self.settings["method_settings"].get("phone", {})
        code = generate_code(method_settings.get("length", 6), "numeric")
        store_challenge(interaction.user.id, code)

        try:
            await send_verification_sms(number, code, interaction.guild.name)
        except SMSNotConfigured:
            await interaction.response.send_message(
                "Phone verification isn't fully set up on this server's bot yet. "
                "Ask an admin to configure Twilio, or try a different verification method.",
                ephemeral=True,
            )
            return
        except SMSSendError:
            await interaction.response.send_message(
                "Couldn't send a text to that number. Double-check it's correct, "
                "or try a different verification method.",
                ephemeral=True,
            )
            return
        except Exception:
            await interaction.response.send_message(
                "Something went wrong sending the code. Please try again in a moment.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Sent a code to {number}. Click below once you have it.",
            view=EnterPhoneCodeView(self.settings),
            ephemeral=True,
        )


class PhoneVerifyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="📱",
            custom_id="verify:phone:click",
        )

    async def callback(self, interaction: discord.Interaction):
        from settings import settings_manager

        guild_settings = await settings_manager.get(interaction.guild_id)

        if not await passes_prechecks(interaction, guild_settings):
            return

        await interaction.response.send_modal(PhoneNumberModal(guild_settings))


class PhoneVerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persists across restarts
        self.add_item(PhoneVerifyButton())


class PhoneVerification(VerificationModule):
    key = "phone"
    display_name = "Phone (SMS)"

    def build_entry_view(self, settings: dict) -> discord.ui.View:
        return PhoneVerificationView()
