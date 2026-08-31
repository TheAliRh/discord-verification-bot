import os
import json
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config import config_manager

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.members = True  # required to detect joins later - enable in Dev Portal too

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    await config_manager.init()
    await bot.tree.sync()
    print(f"Logged in as {bot.user} (id: {bot.user.id})")
    print("Config layer initialized.")


@bot.tree.command(
    name="verify-view", description="View this server's verification config"
)
async def verify_view(interaction: discord.Interaction):
    config = await config_manager.get(interaction.guild_id)
    pretty = json.dumps(config, indent=2)

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
        app_commands.Choice(name="Captcha", value="captcha"),
        app_commands.Choice(name="Math question", value="math"),
    ]
)
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_set_method(
    interaction: discord.Interaction, method: app_commands.Choice[str]
):
    new_config = await config_manager.update(
        interaction.guild_id, {"method": method.value}
    )
    await interaction.response.send_message(
        f"Verification method set to **{new_config['method']}**.", ephemeral=True
    )


@bot.tree.command(
    name="verify-reset",
    description="Reset this server's verification config to defaults",
)
@app_commands.checks.has_permissions(manage_guild=True)
async def verify_reset(interaction: discord.Interaction):
    await config_manager.reset(interaction.guild_id)
    await interaction.response.send_message(
        "Verification config reset to defaults.", ephemeral=True
    )


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Copy .env.example to .env and fill it in."
        )
    bot.run(TOKEN)
