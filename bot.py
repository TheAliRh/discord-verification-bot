import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from settings import settings_manager
from modules import get_module, all_persistent_views, MODULES

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True  # required to detect joins later - enable in Dev Portal too

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await settings_manager.init()

    # Re-register every module's persistent view so buttons on old messages
    # (sent before this restart) still work. Safe to call every startup -
    # discord.py just re-attaches the listener by custom_id.
    for view in all_persistent_views():
        bot.add_view(view)

    await bot.tree.sync()
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("Settings layer initialized. Persistent views registered.")


@bot.tree.command(
    name="verify-view", description="View this server's verification settings"
)
async def verify_view(interaction: discord.Interaction):
    settings = await settings_manager.get(interaction.guild_id)
    pretty = json.dumps(settings, indent=2)

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
    ]
)
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_method(
    interaction: discord.Interaction, method: app_commands.Choice[str]
):
    new_settings = await settings_manager.update(
        interaction.guild_id, {"method": method.value}
    )
    await interaction.response.send_message(
        f"Verification method set to **{new_settings['method']}**.", ephemeral=True
    )


@bot.tree.command(
    name="verify-set-role",
    description="Set the role given to users who pass verification",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_role(interaction: discord.Interaction, role: discord.Role):
    if role >= interaction.guild.me.top_role:
        await interaction.response.send_message(
            "⚠️ My bot's role is not above that role, so I won't be able to assign it. "
            "Move my role higher in Server Settings > Roles, then try again.",
            ephemeral=True,
        )
        return

    await settings_manager.update(interaction.guild_id, {"verified_role_id": role.id})
    await interaction.response.send_message(
        f"Verified role set to {role.mention}.", ephemeral=True
    )


@bot.tree.command(
    name="verify-post", description="Post the verification message in this channel"
)
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_post(interaction: discord.Interaction):
    settings = await settings_manager.get(interaction.guild_id)

    if settings.get("verified_role_id") is None:
        await interaction.response.send_message(
            "Set a Verified role first with `/verify-set-role`.", ephemeral=True
        )
        return

    module = get_module(settings["method"])
    view = module.build_entry_view(settings)

    embed = discord.Embed(
        title="Verification required",
        description=settings.get("welcome_message", "Click below to verify."),
    )
    embed.set_footer(text=f"Method: {MODULES[settings['method']].display_name}")

    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message(
        "Verification message posted.", ephemeral=True
    )


@bot.tree.command(
    name="verify-reset",
    description="Reset this server's verification settings to defaults",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_reset(interaction: discord.Interaction):
    await settings_manager.reset(interaction.guild_id)
    await interaction.response.send_message(
        "Verification settings reset to defaults.", ephemeral=True
    )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Copy .env.example to .env and fill it in."
        )
    bot.run(TOKEN)
