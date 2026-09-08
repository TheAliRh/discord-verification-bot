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
from typing import Any, cast

import discord

from . import attempt_tracker

logger = logging.getLogger(__name__)


async def _log(guild: discord.Guild, settings: dict[str, Any], message: str) -> None:
    log_channel_id = settings.get("log_channel_id")
    if not log_channel_id:
        return
    channel = guild.get_channel(log_channel_id)
    if not isinstance(channel, discord.abc.Messageable):
        # Not every channel type discord.py returns here supports .send()
        # (e.g. CategoryChannel, ForumChannel) - if the configured log
        # channel isn't a postable one, just skip rather than crash.
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


async def log_event(
    guild: discord.Guild, settings: dict[str, Any], message: str
) -> None:
    """
    Public entry point for logging from outside this module - e.g. bot.py's
    on_member_join, which needs to record a join or a role-assignment
    failure without going through grant_verified/deny_verified (nothing
    was verified yet at that point).
    """
    await _log(guild, settings, message)


async def _assign_verified_role(
    guild: discord.Guild, member: discord.Member, settings: dict[str, Any]
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
    attempt_tracker.reset_attempts(guild.id, member.id)
    return True, "You're verified! Welcome to the server."


async def grant_verified(
    interaction: discord.Interaction, settings: dict[str, Any]
) -> None:
    """Interaction-based entry point - used by button/captcha/email/phone modules."""
    guild = interaction.guild

    if guild is None:
        # Every verification component only ever appears on a message inside
        # a guild, so this shouldn't happen in practice - guarded rather than
        # assumed, so a stale/misdirected interaction fails cleanly instead
        # of crashing with an AttributeError deeper in _assign_verified_role.
        await interaction.response.send_message(
            "This can only be used inside a server.", ephemeral=True
        )
        return

    # discord.py guarantees interaction.user is a Member (not a bare User)
    # whenever interaction.guild is set - a cast documents that real contract,
    # rather than an isinstance check that would also (incorrectly) reject
    # legitimate duck-typed test doubles that don't literally subclass Member.
    member = cast(discord.Member, interaction.user)

    ok, message = await _assign_verified_role(guild, member, settings)
    prefix = "✅ " if ok else ""
    await interaction.response.send_message(f"{prefix}{message}", ephemeral=True)


async def grant_verified_by_id(
    bot: discord.Client, guild_id: int, user_id: int, settings: dict[str, Any]
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
    interaction: discord.Interaction,
    settings: dict[str, Any],
    reason: str = "Incorrect answer.",
    *,
    count_as_attempt: bool = True,
    suggest_retry: bool = True,
) -> None:
    """
    Call when a user fails a verification attempt (e.g. wrong captcha code).

    count_as_attempt controls whether this failure counts toward the guild's
    max_attempts limit. Only genuine wrong-guess failures (bad code, expired
    code) should count - a precheck rejection (account too new, already
    locked out) is a different kind of denial and must NOT also consume an
    attempt, or those checks would compound with the attempt limit in a
    confusing way.

    suggest_retry controls whether "Click Verify to try again." is appended -
    set to False when the reason itself already explains why retrying right
    now won't help (e.g. a lockout notice with a cooldown timer).
    """
    logger.info(
        "%s (%s) failed verification in guild %s: %s",
        interaction.user,
        interaction.user.id,
        interaction.guild_id,
        reason,
    )

    guild = interaction.guild
    final_reason = f"{reason} Click Verify to try again." if suggest_retry else reason

    if count_as_attempt and guild is not None:
        max_attempts: int = settings.get("max_attempts", 0)
        if max_attempts > 0:
            attempt_count = attempt_tracker.record_failed_attempt(
                guild.id, interaction.user.id
            )
            remaining = max_attempts - attempt_count

            if remaining > 0:
                final_reason = (
                    f"{reason} {remaining} attempt(s) remaining before a temporary lockout. "
                    "Click Verify to try again."
                )
            else:
                cooldown_seconds: int = settings.get("cooldown_seconds", 30)
                attempt_tracker.lock_out(
                    guild.id, interaction.user.id, cooldown_seconds
                )
                logger.warning(
                    "%s (%s) hit max_attempts (%s) for verification in guild %s",
                    interaction.user,
                    interaction.user.id,
                    max_attempts,
                    guild.id,
                )
                await _log(
                    guild,
                    settings,
                    f"🔒 {interaction.user} locked out after {max_attempts} failed attempts.",
                )

                if settings.get("kick_on_fail", False):
                    member = cast(discord.Member, interaction.user)
                    try:
                        await member.kick(
                            reason=f"Exceeded max verification attempts ({max_attempts})"
                        )
                        final_reason = (
                            f"{reason} You've reached the maximum of {max_attempts} failed attempts "
                            "and have been removed from the server."
                        )
                        logger.warning(
                            "%s (%s) kicked from guild %s after exceeding max_attempts",
                            member,
                            member.id,
                            guild.id,
                        )
                        await _log(
                            guild,
                            settings,
                            f"👢 {member} kicked after exceeding max verification attempts.",
                        )
                    except discord.Forbidden:
                        logger.warning(
                            "Missing permission to kick %s from guild %s",
                            member,
                            guild.id,
                        )
                        await _log(
                            guild,
                            settings,
                            f"⚠️ Missing permission to kick {member} after max attempts.",
                        )
                        final_reason = (
                            f"{reason} You've reached the maximum of {max_attempts} failed attempts. "
                            f"Try again in {cooldown_seconds} second(s)."
                        )
                else:
                    final_reason = (
                        f"{reason} You've reached the maximum of {max_attempts} failed attempts. "
                        f"Try again in {cooldown_seconds} second(s)."
                    )

    await interaction.response.send_message(f"❌ {final_reason}", ephemeral=True)
    if guild is not None:
        await _log(
            guild, settings, f"❌ {interaction.user} failed verification: {reason}"
        )
