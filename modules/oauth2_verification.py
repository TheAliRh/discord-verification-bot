"""
OAuth2 verification.

Flow:
  1. User clicks Verify (after passing shared pre-checks) -> we generate a
     one-time state token bound to (guild_id, user_id) and respond with an
     ephemeral "Continue with Discord" link button.
  2. User's browser follows that link to Discord's OAuth2 consent page,
     approves, and Discord redirects back to our web server's
     /oauth/callback route (see web/server.py).
  3. That route exchanges the code, confirms identity, and grants the role
     directly via core.service.grant_verified_by_id - NOT through another
     Discord interaction, since none exists on that side of the flow.

This module's job ends the moment the link is sent. Everything after that
happens over HTTP, outside of Discord's interaction system entirely.
"""

import discord
from core.base import VerificationModule
from core.prechecks import passes_prechecks
from core.oauth_state import create_state
from core.discord_oauth import build_authorize_url, is_configured, OAuthNotConfigured


class ContinueWithDiscordView(discord.ui.View):
    def __init__(self, authorize_url: str):
        super().__init__(timeout=600)  # matches the state token TTL
        self.add_item(
            discord.ui.Button(
                label="Continue with Discord",
                style=discord.ButtonStyle.link,
                url=authorize_url,
            )
        )


class OAuth2VerifyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="🔗",
            custom_id="verify:oauth2:click",
        )

    async def callback(self, interaction: discord.Interaction):
        from settings import settings_manager

        guild_settings = await settings_manager.get(interaction.guild_id)

        if not await passes_prechecks(interaction, guild_settings):
            return

        if not is_configured():
            await interaction.response.send_message(
                "OAuth2 verification isn't fully set up on this bot yet. Ask an admin to configure it, "
                "or try a different verification method.",
                ephemeral=True,
            )
            return

        state = create_state(interaction.guild_id, interaction.user.id)

        try:
            url = build_authorize_url(state)
        except OAuthNotConfigured:
            await interaction.response.send_message(
                "OAuth2 verification isn't fully set up on this bot yet.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            "Click below to verify with your Discord account:",
            view=ContinueWithDiscordView(url),
            ephemeral=True,
        )


class OAuth2VerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # persists across restarts
        self.add_item(OAuth2VerifyButton())


class OAuth2Verification(VerificationModule):
    key = "oauth2"
    display_name = "OAuth2"

    def build_entry_view(self, settings: dict) -> discord.ui.View:
        return OAuth2VerificationView()
