"""
Shared error handling for Discord UI components (Views and Modals).

This covers a gap that bot.py's @bot.tree.error handler does NOT: that
handler only catches errors raised inside slash commands. Button clicks
and modal submissions go through a completely separate pathway -
discord.ui.View.on_error / discord.ui.Modal.on_error - and without
overriding it, an unhandled exception there is only dumped to stderr by
discord.py's default handler. The user is left staring at Discord's
generic "This interaction failed" with no explanation, and the failure
is easy to miss in a live bot's scrolling console output.

Every View/Modal in modules/ and ui/ subclasses BaseView/BaseModal instead
of discord.ui.View/discord.ui.Modal directly, so this applies uniformly
everywhere without repeating it in every file.
"""

import logging
import discord

logger = logging.getLogger(__name__)

_GENERIC_MESSAGE = "Something went wrong. Please try again, or contact a server admin if this keeps happening."


async def _handle_component_error(
    interaction: discord.Interaction, error: Exception, source: str
):
    logger.error("Unhandled error in %s", source, exc_info=error)

    try:
        if interaction.response.is_done():
            await interaction.followup.send(_GENERIC_MESSAGE, ephemeral=True)
        else:
            await interaction.response.send_message(_GENERIC_MESSAGE, ephemeral=True)
    except discord.HTTPException:
        # Interaction token may have expired (>15 min since the original
        # interaction) - nothing more we can do at that point.
        logger.warning(
            "Could not deliver error message to user - interaction likely expired"
        )


class BaseView(discord.ui.View):
    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item
    ) -> None:
        await _handle_component_error(
            interaction, error, f"{type(self).__name__} ({type(item).__name__})"
        )


class BaseModal(discord.ui.Modal):
    # discord.py's type stub for Modal.on_error incorrectly inherits a
    # 3-argument signature from discord.py's own internal class also named
    # "BaseView" (an unrelated coincidental name collision with ours - see
    # discord.ui.Modal.__mro__). Verified via inspect.signature(discord.ui.Modal.on_error)
    # that the real runtime signature only takes (interaction, error) - this
    # override is correct at runtime; only the stub is wrong.
    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:  # type: ignore[override]
        await _handle_component_error(interaction, error, type(self).__name__)
