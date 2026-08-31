"""
Shared verification service.

Every module calls into here to finish the job once it decides a user
passed or failed. Keeping this in one place means role assignment,
error handling, and logging behave identically no matter which method
(button, captcha, future email/OAuth2/etc.) triggered it.
"""

import discord


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
        pass  # missing permission to post in log channel - fail silently, don't crash verification


async def grant_verified(interaction: discord.Interaction, settings: dict):
    """Call when a user has successfully passed verification."""
    guild = interaction.guild
    member = interaction.user

    verified_role_id = settings.get("verified_role_id")
    unverified_role_id = settings.get("unverified_role_id")

    if verified_role_id is None:
        await interaction.response.send_message(
            "You passed verification, but this server hasn't set a Verified role yet. "
            "Ask an admin to run `/verify-set-role`.",
            ephemeral=True,
        )
        return

    verified_role = guild.get_role(verified_role_id)
    if verified_role is None:
        await interaction.response.send_message(
            "You passed verification, but the set Verified role no longer exists. "
            "Ask an admin to reset it.",
            ephemeral=True,
        )
        await _log(
            guild,
            settings,
            f"⚠️ Verified role {verified_role_id} not found for {member}.",
        )
        return

    try:
        await member.add_roles(verified_role, reason="Passed verification")
        if unverified_role_id:
            unverified_role = guild.get_role(unverified_role_id)
            if unverified_role and unverified_role in member.roles:
                await member.remove_roles(unverified_role, reason="Passed verification")
    except discord.Forbidden:
        await interaction.response.send_message(
            "I don't have permission to assign that role. Ask an admin to move my bot's role "
            "above the Verified role in Server Settings > Roles.",
            ephemeral=True,
        )
        await _log(guild, settings, f"⚠️ Missing permission to assign role to {member}.")
        return

    await interaction.response.send_message(
        "✅ You're verified! Welcome to the server.", ephemeral=True
    )
    await _log(guild, settings, f"✅ {member} ({member.id}) passed verification.")


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
