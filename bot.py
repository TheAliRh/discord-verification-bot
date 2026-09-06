import os
from dotenv import load_dotenv

# Must happen before importing any of our own modules below: core/email_sender.py,
# core/sms_sender.py, and core/discord_oauth.py read credentials from the
# environment as soon as they're imported (not lazily inside a function), so
# .env has to be loaded into os.environ before those imports run - not after.
load_dotenv()

import json
import logging
import discord
from discord import app_commands
from discord.ext import commands

from settings import settings_manager
from modules import get_module, all_persistent_views
from ui import SetupView
from web import start_server
from core import service
from core.logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

TOKEN = os.getenv("DISCORD_TOKEN")
OAUTH_SERVER_PORT = int(os.getenv("OAUTH_SERVER_PORT", "8080"))

intents = discord.Intents.default()
intents.members = True  # required to detect joins later - enable in Dev Portal too


class VerifyBot(commands.Bot):
    async def setup_hook(self) -> None:
        # setup_hook runs exactly once, before the bot connects to the
        # gateway for the first time - unlike on_ready, which discord.py
        # can call again after a dropped gateway connection reconnects.
        # Everything here must be safe to run ONLY once per process, or a
        # reconnect would repeat it: settings_manager.init() would open a
        # second (leaked) database connection without closing the first,
        # add_view() would re-register views that are already registered,
        # and tree.sync() would re-sync commands against Discord's API for
        # no reason, burning rate limit budget every time the gateway blips.
        try:
            await settings_manager.init()
        except Exception:
            logger.critical(
                "Failed to initialize the settings database (data/bot.db). "
                "Check that the 'data/' folder exists and is writable. The bot cannot function without this.",
                exc_info=True,
            )
            raise  # nothing else can work without settings - fail loudly and stop

        # Re-register every module's persistent view so buttons on old messages
        # (sent before this restart) still work.
        for view in all_persistent_views():
            self.add_view(view)

        await self.tree.sync()

        try:
            self.web_runner = await start_server(self, port=OAUTH_SERVER_PORT)
            logger.info(
                "OAuth2 callback server listening on port %s", OAUTH_SERVER_PORT
            )
        except OSError as e:
            logger.error(
                "Could not start the OAuth2 callback server on port %s (%s). "
                "Is another instance of this bot already running, or is that port in use "
                "by something else? OAuth2 verification will not work until this is fixed, "
                "but the rest of the bot will continue starting up.",
                OAUTH_SERVER_PORT,
                e,
            )

        logger.info(
            "Settings layer initialized. Persistent views registered. Commands synced."
        )


bot = VerifyBot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    # This CAN fire more than once per process (e.g. after a dropped gateway
    # connection reconnects) - only safe, idempotent logging belongs here.
    # All one-time startup work lives in setup_hook() above, which discord.py
    # guarantees runs exactly once.
    if bot.user is not None:
        logger.info("Logged in as %s (id: %s)", bot.user, bot.user.id)


@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "You need the **Manage Server** permission to use this command.",
            ephemeral=True,
        )
        return

    if isinstance(error, app_commands.NoPrivateMessage):
        await interaction.response.send_message(
            "This command only works inside a server, not in DMs.", ephemeral=True
        )
        return

    # Anything else is unexpected - log it with a full traceback so it's
    # not silently lost, and give the user a generic message instead of
    # Discord's raw error screen.
    command_name = interaction.command.name if interaction.command else "unknown"
    logger.error("Unhandled error in /%s", command_name, exc_info=error)

    if not interaction.response.is_done():
        await interaction.response.send_message(
            "Something went wrong running that command.", ephemeral=True
        )


@bot.event
async def on_member_join(member: discord.Member) -> None:
    guild_settings = await settings_manager.get(member.guild.id)

    if not guild_settings.get("enabled", True):
        logger.debug(
            "Verification disabled for guild %s, skipping on_member_join for %s",
            member.guild.id,
            member,
        )
        return  # verification turned off entirely for this guild

    unverified_role_id = guild_settings.get("unverified_role_id")
    if unverified_role_id:
        role = member.guild.get_role(unverified_role_id)
        if role is None:
            logger.warning(
                "Configured Unverified role %s not found in guild %s for new member %s",
                unverified_role_id,
                member.guild.id,
                member,
            )
            await service.log_event(
                member.guild,
                guild_settings,
                f"⚠️ Configured Unverified role {unverified_role_id} not found for new member {member}.",
            )
        else:
            try:
                await member.add_roles(role, reason="New member - pending verification")
            except discord.Forbidden:
                logger.warning(
                    "Missing permission to assign Unverified role to %s in guild %s",
                    member,
                    member.guild.id,
                )
                await service.log_event(
                    member.guild,
                    guild_settings,
                    f"⚠️ Missing permission to assign Unverified role to {member} on join.",
                )

    verify_channel_id = guild_settings.get("verify_channel_id")
    channel_mention = (
        f"<#{verify_channel_id}>" if verify_channel_id else "the verification channel"
    )

    try:
        await member.send(
            f"Welcome to **{member.guild.name}**! Head to {channel_mention} to verify and get full access."
        )
    except discord.Forbidden:
        logger.debug("Could not DM %s on join (DMs closed) - not an error", member)

    logger.info("%s (%s) joined guild %s", member, member.id, member.guild.id)
    await service.log_event(
        member.guild,
        guild_settings,
        f"👋 {member} ({member.id}) joined."
        + (
            " Unverified role assigned."
            if unverified_role_id
            else " No Unverified role configured."
        ),
    )


verify_group = app_commands.Group(name="verify", description="Verification setup")


@verify_group.command(
    name="setup", description="Interactive setup wizard for verification"
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_setup(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        return  # guild_only() already enforces this; narrows the type for mypy too
    current_settings = await settings_manager.get(interaction.guild.id)
    view = SetupView(current_settings)
    await interaction.response.send_message(
        embed=view.build_embed(), view=view, ephemeral=True
    )


bot.tree.add_command(verify_group)


@bot.tree.command(
    name="verify-view", description="View this server's verification settings"
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_view(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        return
    guild_settings = await settings_manager.get(interaction.guild.id)
    pretty = json.dumps(guild_settings, indent=2)

    if len(pretty) > 1900:
        pretty = pretty[:1900] + "\n... (truncated)"

    await interaction.response.send_message(f"```json\n{pretty}\n```", ephemeral=True)


@bot.tree.command(
    name="verify-set-method", description="Set the verification method for this server"
)
@app_commands.describe(method="Verification method to use")
@app_commands.choices(
    method=[
        app_commands.Choice(name="Button", value="button"),
        app_commands.Choice(name="Captcha (text)", value="captcha"),
        app_commands.Choice(name="Captcha (image)", value="image_captcha"),
        app_commands.Choice(name="Email", value="email"),
        app_commands.Choice(name="Phone (SMS)", value="phone"),
        app_commands.Choice(name="OAuth2", value="oauth2"),
    ]
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_method(
    interaction: discord.Interaction, method: app_commands.Choice[str]
) -> None:
    if interaction.guild is None:
        return
    new_settings = await settings_manager.update(
        interaction.guild.id, {"method": method.value}
    )
    await interaction.response.send_message(
        f"Verification method set to **{new_settings['method']}**.", ephemeral=True
    )


@bot.tree.command(
    name="verify-set-role",
    description="Set the role given to users who pass verification",
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_role(interaction: discord.Interaction, role: discord.Role) -> None:
    if interaction.guild is None:
        return

    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            "⚠️ My bot's role is not above that role, so I won't be able to assign it. "
            "Move my role higher in Server Settings > Roles, then try again.",
            ephemeral=True,
        )
        return

    await settings_manager.update(interaction.guild.id, {"verified_role_id": role.id})
    await interaction.response.send_message(
        f"Verified role set to {role.mention}.", ephemeral=True
    )


@bot.tree.command(
    name="verify-set-unverified-role",
    description="Set the role new members get until they pass verification",
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_unverified_role(
    interaction: discord.Interaction, role: discord.Role
) -> None:
    if interaction.guild is None:
        return

    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            "⚠️ My bot's role is not above that role, so I won't be able to assign it. "
            "Move my role higher in Server Settings > Roles, then try again.",
            ephemeral=True,
        )
        return

    await settings_manager.update(interaction.guild.id, {"unverified_role_id": role.id})
    await interaction.response.send_message(
        f"Unverified role set to {role.mention}. New members will get this automatically on join.\n"
        "Remember to also deny **View Channel** for this role on any channels you want hidden "
        "until verification - assigning the role alone doesn't hide anything by itself.",
        ephemeral=True,
    )


@bot.tree.command(
    name="verify-set-min-age",
    description="Require a minimum Discord account age (in days) before someone can verify",
)
@app_commands.describe(days="Minimum account age in days. Use 0 to disable this check.")
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_min_age(
    interaction: discord.Interaction, days: app_commands.Range[int, 0, 3650]
) -> None:
    if interaction.guild is None:
        return

    await settings_manager.update(interaction.guild.id, {"min_account_age_days": days})

    if days == 0:
        await interaction.response.send_message(
            "Minimum account age check disabled.", ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"Users must now have a Discord account at least **{days} day(s)** old to verify.",
            ephemeral=True,
        )


@bot.tree.command(
    name="verify-post",
    description="Post the verification message in the configured verification channel",
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_post(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        return

    guild_settings = await settings_manager.get(interaction.guild.id)

    if guild_settings.get("verified_role_id") is None:
        await interaction.response.send_message(
            "Set a Verified role first with `/verify-set-role`.", ephemeral=True
        )
        return

    # get_module() already falls back to Button for an unknown/invalid stored
    # method, so module.display_name below is always safe - unlike indexing
    # MODULES[guild_settings["method"]] directly, which would raise KeyError
    # on the exact same invalid value this line is guarding against.
    module = get_module(guild_settings["method"])
    view = module.build_entry_view(guild_settings)

    embed = discord.Embed(
        title="Verification required",
        description=guild_settings.get("welcome_message", "Click below to verify."),
    )
    embed.set_footer(text=f"Method: {module.display_name}")

    min_age_days = guild_settings.get("min_account_age_days", 0)
    if min_age_days > 0:
        embed.add_field(
            name="Requirement",
            value=f"Your Discord account must be at least {min_age_days} day(s) old.",
            inline=False,
        )

    # Post in the channel configured via /verify setup, not wherever this
    # command happened to be run - falling back to the current channel only
    # if none is configured, or the configured one is no longer usable.
    verify_channel_id = guild_settings.get("verify_channel_id")
    target_channel: discord.abc.Messageable | None = None
    fallback_warning: str | None = None

    if verify_channel_id is not None:
        configured_channel = interaction.guild.get_channel(verify_channel_id)
        if configured_channel is None:
            fallback_warning = (
                f"⚠️ The configured verification channel (<#{verify_channel_id}>) no longer exists - "
                "posted here instead. Run `/verify setup` to pick a new one."
            )
        elif not isinstance(configured_channel, discord.abc.Messageable):
            fallback_warning = (
                f"⚠️ The configured verification channel (<#{verify_channel_id}>) isn't a channel "
                "type I can post in - posted here instead. Run `/verify setup` to pick a new one."
            )
        else:
            target_channel = configured_channel

    if target_channel is None:
        if not isinstance(interaction.channel, discord.abc.Messageable):
            await interaction.response.send_message(
                "This can't be posted in this type of channel, and no valid verification "
                "channel is configured. Run `/verify setup` to pick one.",
                ephemeral=True,
            )
            return
        target_channel = interaction.channel

    try:
        await target_channel.send(embed=embed, view=view)
    except discord.Forbidden:
        channel_mention = getattr(target_channel, "mention", "that channel")
        await interaction.response.send_message(
            f"I don't have permission to post in {channel_mention}. Check my channel permissions there.",
            ephemeral=True,
        )
        return

    channel_mention = getattr(target_channel, "mention", "this channel")
    confirmation = f"Verification message posted in {channel_mention}."
    if fallback_warning:
        confirmation = f"{fallback_warning}\n{confirmation}"
    await interaction.response.send_message(confirmation, ephemeral=True)


@bot.tree.command(
    name="verify-reset",
    description="Reset this server's verification settings to defaults",
)
@app_commands.guild_only()
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_reset(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        return
    await settings_manager.reset(interaction.guild.id)
    await interaction.response.send_message(
        "Verification settings reset to defaults.", ephemeral=True
    )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Copy .env.example to .env and fill it in."
        )
    # log_handler=None: our own setup_logging() already configured the root
    # logger (console + rotating file). Without this, discord.py adds its
    # own separate console handler and every log line prints twice.
    bot.run(TOKEN, log_handler=None)
