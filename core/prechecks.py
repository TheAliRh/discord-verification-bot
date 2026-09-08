"""
Shared pre-checks - run before ANY verification module does its own thing.

These are checks that apply no matter which method (button, captcha, future
email/OAuth2/etc.) the guild has configured. Keeping them here means every
module enforces them identically, and adding a new stackable check later
(e.g. no-default-avatar, blacklist lookup) only means editing this one file.

Usage in a module's entry-point callback:

    guild_settings = await settings_manager.get(interaction.guild_id)
    if not await passes_prechecks(interaction, guild_settings):
        return   # denial message already sent inside passes_prechecks
    # ... proceed with this module's own verification flow
"""

from typing import Any

import discord
from . import service
from . import attempt_tracker


async def passes_prechecks(
    interaction: discord.Interaction, guild_settings: dict[str, Any]
) -> bool:
    """
    Returns True if the user may proceed to the verification module's own
    flow. If a check fails, this sends the denial message itself (via
    core.service.deny_verified) and returns False - callers should just
    `return` immediately when this returns False.
    """
    if not guild_settings.get("enabled", True):
        # Verification turned off entirely for this guild. on_member_join()
        # already skips assigning the Unverified role/DM for new joins when
        # this is False, but that alone doesn't stop someone from clicking
        # an already-posted Verify button - this is the check that actually
        # closes that gap.
        await service.deny_verified(
            interaction,
            guild_settings,
            "Verification is currently turned off on this server. Contact a staff member if you need access.",
            count_as_attempt=False,  # not a wrong guess, verification isn't even running
            suggest_retry=False,  # retrying won't help until an admin re-enables it
        )
        return False

    if interaction.guild_id is not None:
        locked, remaining_seconds = attempt_tracker.is_locked_out(
            interaction.guild_id, interaction.user.id
        )
        if locked:
            await service.deny_verified(
                interaction,
                guild_settings,
                f"Too many failed attempts. Try again in {int(remaining_seconds) + 1} second(s).",
                count_as_attempt=False,  # already locked out - don't double-penalize
                suggest_retry=False,  # retrying right now won't work, the message already says when it will
            )
            return False

    if not _passes_account_age(interaction, guild_settings):
        min_age_days = guild_settings.get("min_account_age_days", 0)
        account_age_days = _account_age_days(interaction.user)
        await service.deny_verified(
            interaction,
            guild_settings,
            f"Your Discord account must be at least {min_age_days} day(s) old to verify here "
            f"(yours is {account_age_days} day(s) old).",
            count_as_attempt=False,  # this isn't a wrong guess, it's a different kind of rejection
        )
        return False

    return True


def _account_age_days(user: discord.User | discord.Member) -> int:
    return (discord.utils.utcnow() - user.created_at).days


def _passes_account_age(
    interaction: discord.Interaction, guild_settings: dict[str, Any]
) -> bool:
    min_age_days: int = guild_settings.get("min_account_age_days", 0)
    if min_age_days <= 0:
        return True  # check disabled

    return _account_age_days(interaction.user) >= min_age_days
