"""
Email verification.

Flow:
  1. User clicks Verify (after passing shared pre-checks) -> modal asks for
     their email address.
  2. We generate a code (same shared challenge_store as the captcha modules),
     email it via core/email_sender.py, and show an "Enter Code" button.
  3. Clicking that opens a second modal for the code -> checked the same way
     every other captcha-style module checks it.

Requires SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD in .env. If unset, users
get a clear "not available" message instead of a silent failure.
"""

import discord
from core.base import VerificationModule
from core import service
from core.prechecks import passes_prechecks
from core.challenge_store import generate_code, store_challenge, check_answer
from core.email_sender import send_verification_email, EmailNotConfigured


def _looks_like_email(address: str) -> bool:
    # Deliberately simple - real validation happens by virtue of whether
    # the email actually arrives. This just catches obvious typos.
    if " " in address or address.count("@") != 1:
        return False
    local, _, domain = address.partition("@")
    if not local or "." not in domain:
        return False
    domain_parts = domain.split(".")
    return all(part for part in domain_parts) and len(domain_parts) >= 2


class EnterEmailCodeModal(discord.ui.Modal, title="Enter the code we emailed you"):
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


class EnterEmailCodeButton(discord.ui.Button):
    def __init__(self, settings: dict):
        super().__init__(label="Enter Code", style=discord.ButtonStyle.primary)
        self.settings = settings

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EnterEmailCodeModal(self.settings))


class EnterEmailCodeView(discord.ui.View):
    def __init__(self, settings: dict):
        super().__init__(timeout=300)
        self.add_item(EnterEmailCodeButton(settings))


class EmailAddressModal(discord.ui.Modal, title="Verify by Email"):
    email = discord.ui.TextInput(
        label="Your email address", placeholder="you@example.com"
    )

    def __init__(self, settings: dict):
        super().__init__()
        self.settings = settings

    async def on_submit(self, interaction: discord.Interaction):
        address = self.email.value.strip()

        if not _looks_like_email(address):
            await interaction.response.send_message(
                "That doesn't look like a valid email address. Click Verify to try again.",
                ephemeral=True,
            )
            return

        method_settings = self.settings["method_settings"].get("email", {})
        code = generate_code(method_settings.get("length", 6), "alphanumeric")
        store_challenge(interaction.user.id, code)

        try:
            await send_verification_email(address, code, interaction.guild.name)
        except EmailNotConfigured:
            await interaction.response.send_message(
                "Email verification isn't fully set up on this server's bot yet. "
                "Ask an admin to configure SMTP, or try a different verification method.",
                ephemeral=True,
            )
            return
        except Exception:
            await interaction.response.send_message(
                "Something went wrong sending the email. Please try again in a moment.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            f"Sent a code to {address}. Click below once you have it.",
            view=EnterEmailCodeView(self.settings),
            ephemeral=True,
        )


class EmailVerifyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="📧",
            custom_id="verify:email:click",
        )

    async def callback(self, interaction: discord.Interaction):
        from settings import settings_manager

        guild_settings = await settings_manager.get(interaction.guild_id)

        if not await passes_prechecks(interaction, guild_settings):
            return

        await interaction.response.send_modal(EmailAddressModal(guild_settings))


class EmailVerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persists across restarts
        self.add_item(EmailVerifyButton())


class EmailVerification(VerificationModule):
    key = "email"
    display_name = "Email"

    def build_entry_view(self, settings: dict) -> discord.ui.View:
        return EmailVerificationView()
