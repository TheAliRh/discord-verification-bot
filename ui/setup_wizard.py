"""
/verify setup wizard.

Instead of several separate slash commands with typed arguments
(/verify-set-method, /verify-set-role, ...), this presents one interactive
message with native Discord select menus for method/role/channel, plus a
button that opens a modal for the welcome message text. Everything is saved
in a single write when "Save Setup" is pressed.
"""

from typing import Any

import discord
from settings import settings_manager
from modules import MODULES
from core.ui_base import BaseView, BaseModal


def _method_options() -> list[discord.SelectOption]:
    return [
        discord.SelectOption(
            label=module.display_name,
            value=key,
            description=f"Use {module.display_name} to verify new members",
        )
        for key, module in MODULES.items()
    ]


class WelcomeMessageModal(BaseModal, title="Customize Welcome Message"):
    message: discord.ui.TextInput[Any] = discord.ui.TextInput(
        label="Message shown above the Verify button",
        style=discord.TextStyle.paragraph,
        max_length=300,
        required=True,
    )

    def __init__(self, wizard_view: "SetupView"):
        super().__init__()
        self.wizard_view = wizard_view
        self.message.default = wizard_view.welcome_message

    async def on_submit(self, interaction: discord.Interaction) -> None:
        self.wizard_view.welcome_message = self.message.value
        await interaction.response.edit_message(
            embed=self.wizard_view.build_embed(), view=self.wizard_view
        )


class MethodSelect(discord.ui.Select):
    def __init__(self, wizard_view: "SetupView"):
        self.wizard_view = wizard_view
        super().__init__(
            placeholder="Choose a verification method...",
            options=_method_options(),
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.wizard_view.method = self.values[0]
        await interaction.response.edit_message(
            embed=self.wizard_view.build_embed(), view=self.wizard_view
        )


class VerifiedRoleSelect(discord.ui.RoleSelect):
    def __init__(self, wizard_view: "SetupView"):
        self.wizard_view = wizard_view
        super().__init__(
            placeholder="Choose the Verified role...", min_values=1, max_values=1, row=1
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return  # this select only ever appears on a message inside a guild

        role = self.values[0]
        if role >= interaction.guild.me.top_role:
            await interaction.response.send_message(
                "⚠️ My role isn't above that role, so I can't assign it. "
                "Move my role higher in Server Settings > Roles, then pick again.",
                ephemeral=True,
            )
            return
        self.wizard_view.verified_role_id = role.id
        await interaction.response.edit_message(
            embed=self.wizard_view.build_embed(), view=self.wizard_view
        )


class VerifyChannelSelect(discord.ui.ChannelSelect):
    def __init__(self, wizard_view: "SetupView"):
        self.wizard_view = wizard_view
        super().__init__(
            placeholder="Choose the channel to post verification in...",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        self.wizard_view.verify_channel_id = self.values[0].id
        await interaction.response.edit_message(
            embed=self.wizard_view.build_embed(), view=self.wizard_view
        )


class EditWelcomeMessageButton(discord.ui.Button):
    def __init__(self, wizard_view: "SetupView"):
        self.wizard_view = wizard_view
        super().__init__(
            label="Edit Welcome Message", style=discord.ButtonStyle.secondary, row=3
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(WelcomeMessageModal(self.wizard_view))


class FinishSetupButton(discord.ui.Button):
    def __init__(self, wizard_view: "SetupView"):
        self.wizard_view = wizard_view
        super().__init__(label="Save Setup", style=discord.ButtonStyle.success, row=3)

    async def callback(self, interaction: discord.Interaction) -> None:
        wizard = self.wizard_view

        if wizard.verified_role_id is None or wizard.verify_channel_id is None:
            await interaction.response.send_message(
                "Please choose both a Verified role and a channel before saving.",
                ephemeral=True,
            )
            return

        if interaction.guild_id is None:
            return  # this button only ever appears on a message inside a guild

        await settings_manager.update(
            interaction.guild_id,
            {
                "method": wizard.method,
                "verified_role_id": wizard.verified_role_id,
                "verify_channel_id": wizard.verify_channel_id,
                "welcome_message": wizard.welcome_message,
            },
        )

        for child in wizard.children:
            child.disabled = True  # type: ignore[attr-defined]  # every child here is a Button/Select, which has .disabled
        wizard.stop()

        await interaction.response.edit_message(
            content="✅ Verification configured! Run `/verify-post` in the channel you chose to publish the message.",
            embed=wizard.build_embed(final=True),
            view=wizard,
        )


class CancelSetupButton(discord.ui.Button):
    def __init__(self, wizard_view: "SetupView"):
        self.wizard_view = wizard_view
        super().__init__(label="Cancel", style=discord.ButtonStyle.danger, row=3)

    async def callback(self, interaction: discord.Interaction) -> None:
        for child in self.wizard_view.children:
            child.disabled = True  # type: ignore[attr-defined]  # every child here is a Button/Select, which has .disabled
        self.wizard_view.stop()
        await interaction.response.edit_message(
            content="Setup cancelled. Nothing was changed.",
            embed=None,
            view=self.wizard_view,
        )


class SetupView(BaseView):
    """
    Not persistent (timeout=300) - unlike the verification message itself,
    the setup wizard only needs to survive one admin's active session.
    """

    def __init__(self, current_settings: dict):
        super().__init__(timeout=300)
        self.method = current_settings.get("method", "button")
        self.verified_role_id = current_settings.get("verified_role_id")
        self.verify_channel_id = current_settings.get("verify_channel_id")
        self.welcome_message = current_settings.get(
            "welcome_message", "Click below to verify and get access to the server."
        )

        self.add_item(MethodSelect(self))
        self.add_item(VerifiedRoleSelect(self))
        self.add_item(VerifyChannelSelect(self))
        self.add_item(EditWelcomeMessageButton(self))
        self.add_item(FinishSetupButton(self))
        self.add_item(CancelSetupButton(self))

    def build_embed(self, final: bool = False) -> discord.Embed:
        embed = discord.Embed(
            title="Verification configured" if final else "Verification setup"
        )

        module = MODULES.get(self.method)
        method_label = module.display_name if module else self.method

        embed.add_field(name="Method", value=method_label, inline=True)
        embed.add_field(
            name="Verified role",
            value=(
                f"<@&{self.verified_role_id}>" if self.verified_role_id else "*not set*"
            ),
            inline=True,
        )
        embed.add_field(
            name="Verify channel",
            value=(
                f"<#{self.verify_channel_id}>"
                if self.verify_channel_id
                else "*not set*"
            ),
            inline=True,
        )
        embed.add_field(
            name="Welcome message", value=self.welcome_message, inline=False
        )

        if not final:
            embed.set_footer(
                text="Pick a method, role, and channel, then press Save Setup."
            )

        return embed

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True  # type: ignore[attr-defined]  # every child here is a Button/Select, which has .disabled
