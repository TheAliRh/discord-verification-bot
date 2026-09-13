"""
Shared role validation for anywhere an admin picks a Verified/Unverified
role - currently /verify-set-role, /verify-set-unverified-role, and the
/verify setup wizard's role select menu.

Centralized here instead of duplicated per call site, since a role that's
unsafe to use in one of these places is unsafe in all of them, and a role
that passes validation in one should behave identically wherever it's used.
"""

import discord


def validate_assignable_role(guild: discord.Guild, role: discord.Role) -> str | None:
    """
    Returns None if the role is safe to use as a Verified/Unverified role.
    Otherwise returns a human-readable reason it was rejected, suitable to
    show directly to the admin who picked it.
    """
    if role.is_default():
        # @everyone. Every member already "has" it implicitly - it can't be
        # meaningfully added/removed, and using it here would apply to
        # literally every member (and bot) in the server unconditionally.
        return (
            "@everyone can't be used here - it's not a real assignable role, "
            "and using it would affect literally everyone in the server."
        )

    if role.managed:
        # Roles owned by an integration (a bot's own role, a Nitro booster
        # role, a linked Twitch/YouTube subscriber role, etc.). Discord's
        # API rejects manually assigning/removing these regardless of the
        # bot's permissions or role position - only the owning integration
        # can change who has them.
        return (
            f"{role.mention} is managed by an integration (a bot, Nitro boost, or linked account) "
            "and can't be manually assigned. Pick a regular role instead."
        )

    bot_member = guild.me

    if not bot_member.guild_permissions.manage_roles:
        # Missing the permission entirely - no role position could fix this.
        return "I don't have the **Manage Roles** permission in this server at all. Grant it to my role first."

    if role >= bot_member.top_role:
        # Have the permission, but this specific role sits at or above the
        # bot's own top role - Discord's hierarchy rule blocks assigning it
        # regardless of the Manage Roles permission.
        return (
            f"My role isn't above {role.mention}, so I can't assign it. "
            "Move my role higher in Server Settings > Roles, then try again."
        )

    return None
