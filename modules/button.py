"""
Button verification.

Simplest method: user clicks a button, they're immediately verified.
No challenge, no state to track between interactions.
"""

import discord
from core.base import VerificationModule
from core import service


class VerifyButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Verify",
            style=discord.ButtonStyle.success,
            emoji="✅",
            # Static custom_id (no per-guild data baked in) is required for
            # the button to survive a bot restart via bot.add_view().
            custom_id="verify:button:click",
        )

    async def callback(self, interaction: discord.Interaction):
        # Settings is looked up fresh at click-time, not baked into the view,
        # so one persistent view definition works correctly for every guild.
        from settings import settings_manager

        settings = await settings_manager.get(interaction.guild_id)
        await service.grant_verified(interaction, settings)


class ButtonVerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)  # timeout=None -> persists across restarts
        self.add_item(VerifyButton())


class ButtonVerification(VerificationModule):
    key = "button"
    display_name = "Button"

    def build_entry_view(self, settings: dict) -> discord.ui.View:
        return ButtonVerificationView()
