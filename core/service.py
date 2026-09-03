"""
Shared verification service.

Every module calls into here to finish the job once it decides a user
passed or failed. Keeping this in one place means role assignment,
error handling, and logging behave identically no matter which method
(button, captcha, email, phone, OAuth2) triggered it.

The actual role-assignment logic lives in _assign_verified_role(), which
is deliberately independent of *how* the caller wants to report the
result. That's what lets both an interaction-based module (button click,
modal submit) and the OAuth2 HTTP callback (no interaction object exists
there at all) share identical behavior instead of two parallel
implementations that could quietly drift apart.
"""

import logging
import discord

logger = logging.getLogger(__name__)


async def _log(guild: discord.Guild, settings: dict, message: str):
    log_channel_id = settings.get("log_channel_id")
    if not log_channel_id:
        return
    channel = guild.get_channel(log_channel_id)
    if channel is None:
        return
    try:
        await channel.send(message)
    except discord.Forbidden:
        # Missing permission to post in the configured log channel - don't
        # crash verification over it, but don't lose the event silently either.
        logger.warning(
            "Missing permission to post in log channel %s (guild %s)",
            log_channel_id,
            guild.id,
        )


async def log_event(guild: discord.Guild, settings: dict, message: str):
    """
    Public entry point for logging from outside this module - e.g. bot.py's
    on_member_join, which needs to record a join or a role-assignment
    failure without going through grant_verified/deny_verified (nothing
    was verified yet at that point).
    """
    await _log(guild, settings, message)


async def _assign_verified_role(
    guild: discord.Guild, member: discord.Member, settings: dict
) -> tuple[bool, str]:
    """
    Core role-assignment logic, returning (success, human-readable message)
    instead of sending anything itself - callers decide how to deliver it
    (an ephemeral Discord message, or an HTML page for the OAuth2 flow).
    """
    verified_role_id = settings.get("verified_role_id")
    unverified_role_id = settings.get("unverified_role_id")

    if verified_role_id is None:
        logger.info(
            "Guild %s has no verified_role_id configured; denying %s", guild.id, member
        )
        return (
            False,
            "This server hasn't set a Verified role yet. Ask an admin to run /verify-set-role.",
        )

    verified_role = guild.get_role(verified_role_id)
    if verified_role is None:
        logger.warning(
            "Verified role %s not found in guild %s for %s",
            verified_role_id,
            guild.id,
            member,
        )
        await _log(
            guild,
            settings,
            f"⚠️ Verified role {verified_role_id} not found for {member}.",
        )
        return (
            False,
            "The set Verified role no longer exists. Ask an admin to reconfigure it.",
        )

    try:
        await member.add_roles(verified_role, reason="Passed verification")
        if unverified_role_id:
            unverified_role = guild.get_role(unverified_role_id)
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Passed verification")
    except discord.Forbidden:
        logger.warning(
            "Missing permission to assign role %s to %s in guild %s",
            verified_role_id,
            member,
            guild.id,
        )
        await _log(guild, settings, f"⚠️ Missing permission to assign role to {member}.")
        return False, (
            "I don't have permission to assign that role. Ask an admin to move my bot's role "
            "above the Verified role in Server Settings > Roles."
        )

    logger.info("%s (%s) passed verification in guild %s", member, member.id, guild.id)
    await _log(guild, settings, f"✅ {member} ({member.id}) passed verification.")
    return True, "You're verified! Welcome to the server."


async def grant_verified(interaction: discord.Interaction, settings: dict):
    """Interaction-based entry point - used by button/captcha/email/phone modules."""
    ok, message = await _assign_verified_role(
        interaction.guild, interaction.user, settings
    )
    prefix = "✅ " if ok else ""
    await interaction.response.send_message(f"{prefix}{message}", ephemeral=True)


async def grant_verified_by_id(
    bot: discord.Client, guild_id: int, user_id: int, settings: dict
) -> tuple[bool, str]:
    """
    Non-interaction entry point - used by the OAuth2 web callback (web/server.py),
    which has no Discord interaction to respond to since the browser hit an
    HTTP route, not a Discord component.
    """
    guild = bot.get_guild(guild_id)
    if guild is None:
        return False, "Could not find that server. Is the bot still a member of it?"

    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except discord.NotFound:
            return False, "Could not find you as a member of that server."

    return await _assign_verified_role(guild, member, settings)


async def deny_verified(
    interaction: discord.Interaction, settings: dict, reason: str = "Incorrect answer."
):
    """Call when a user fails a verification attempt (e.g. wrong captcha code)."""
    await interaction.response.send_message(
        f"❌ {reason} Click Verify to try again.", ephemeral=True
    )
    await _log(
        interaction.guild,
        settings,
        f"❌ {interaction.user} failed verification: {reason}",
    )
