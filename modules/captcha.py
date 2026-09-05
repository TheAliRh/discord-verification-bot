"""
Text captcha.

User clicks Verify (after passing shared pre-checks, e.g. minimum account
age) -> we generate a random code and show it in a modal text field's
label -> user types it back -> we check it matches.

No image generation - the code is dependency-free but weak, since the
code sits in plain text right on the form. See modules/image_captcha.py
for a version that actually requires reading a distorted image.
"""

import discord
from core.base import VerificationModule
from core import service
from core.prechecks import passes_prechecks
from core.challenge_store import generate_code, store_challenge, check_answer
from core.ui_base import BaseView, BaseModal


class CaptchaModal(BaseModal, title="Verification Captcha"):
    def __init__(self, expected_code: str, settings: dict):
        super().__init__()
        self.settings = settings
        self.answer = discord.ui.TextInput(
            label=f"Type this code: {expected_code}",
            placeholder="e.g. AB3XZ9",
            min_length=len(expected_code),
            max_length=len(expected_code),
        )
        self.add_item(self.answer)

    async def on_submit(self, interaction: discord.Interaction):
        passed, reason = check_answer(interaction.user.id, self.answer.value)
        if passed:
            await service.grant_verified(interaction, self.settings)
        else:
            await service.deny_verified(interaction, self.settings, reason)


class CaptchaButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="🔐",
            custom_id="verify:captcha:click",
        )

    async def callback(self, interaction: discord.Interaction):
        from settings import settings_manager

        guild_settings = await settings_manager.get(interaction.guild_id)

        if not await passes_prechecks(interaction, guild_settings):
            return

        method_settings = guild_settings["method_settings"]["captcha"]
        code = generate_code(
            method_settings.get("length", 6),
            method_settings.get("type", "alphanumeric"),
        )
        store_challenge(interaction.user.id, code)

        await interaction.response.send_modal(CaptchaModal(code, guild_settings))


class CaptchaVerificationView(BaseView):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CaptchaButton())


class CaptchaVerification(VerificationModule):
    key = "captcha"
    display_name = "Captcha (text)"

    def build_entry_view(self, settings: dict) -> discord.ui.View:
        return CaptchaVerificationView()
