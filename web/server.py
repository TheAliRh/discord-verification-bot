"""
Minimal web server hosting the OAuth2 callback route.

Runs inside the same asyncio event loop as the bot (started from
bot.py's setup_hook), so the callback handler can call straight into
discord.py (fetch guilds/members, assign roles) with no separate process
or IPC needed.

IMPORTANT - localhost vs public hosting:
http://localhost:PORT/oauth/callback only resolves on the machine the bot
is running on. That's fine while YOU are the one completing OAuth2 for
testing (same PC, same browser). For other server members to use this
method, the bot needs to run somewhere with a public HTTPS URL (a VPS,
Railway, etc.) and OAUTH_REDIRECT_URI/the Discord app's redirect settings
need to point at that public URL instead.
"""

import logging

from aiohttp import web

from settings import settings_manager
from core.oauth_state import consume_state
from core.discord_oauth import exchange_code_for_token, fetch_discord_user
from core import service

logger = logging.getLogger(__name__)


def _html(title: str, message: str, status: int = 200) -> web.Response:
    body = f"""<!DOCTYPE html>
<html>
<head><title>{title}</title></head>
<body style="font-family: sans-serif; text-align: center; padding-top: 80px;">
<h2>{title}</h2>
<p>{message}</p>
<p>You can close this tab and return to Discord.</p>
</body>
</html>"""
    return web.Response(text=body, content_type="text/html", status=status)


async def oauth_callback(request: web.Request) -> web.Response:
    bot = request.app["bot"]

    if request.query.get("error"):
        return _html(
            "Verification cancelled",
            "You didn't complete the authorization.",
            status=400,
        )

    code = request.query.get("code")
    state_token = request.query.get("state")
    if not code or not state_token:
        logger.warning("OAuth2 callback hit with missing code/state parameter")
        return _html("Invalid request", "Missing code or state parameter.", status=400)

    state = consume_state(state_token)
    if state is None:
        logger.warning("OAuth2 callback with an invalid or expired state token")
        return _html(
            "Link expired",
            "This verification link expired or was already used. "
            "Go back to Discord and click Verify again.",
            status=400,
        )

    try:
        access_token = await exchange_code_for_token(code)
        discord_user = await fetch_discord_user(access_token)
    except Exception:
        logger.exception("OAuth2 token exchange or identity fetch failed")
        return _html(
            "Something went wrong",
            "Couldn't complete verification with Discord. Please try again.",
            status=502,
        )

    # Confirm the account that actually authorized matches who clicked Verify -
    # prevents someone else's completed OAuth flow from verifying the wrong user.
    if str(discord_user.get("id")) != str(state["user_id"]):
        logger.warning(
            "OAuth2 identity mismatch: expected user %s, got %s (guild %s)",
            state["user_id"],
            discord_user.get("id"),
            state["guild_id"],
        )
        return _html(
            "Account mismatch",
            "You authorized with a different Discord account than the one that started verification.",
            status=403,
        )

    guild_settings = await settings_manager.get(state["guild_id"])
    ok, message = await service.grant_verified_by_id(
        bot, state["guild_id"], state["user_id"], guild_settings
    )

    logger.info(
        "OAuth2 callback completed for user %s in guild %s: ok=%s",
        state["user_id"],
        state["guild_id"],
        ok,
    )
    title = "You're verified! ✅" if ok else "Verification failed"
    return _html(title, message, status=200 if ok else 400)


def create_app(bot) -> web.Application:
    app = web.Application()
    app["bot"] = bot
    app.router.add_get("/oauth/callback", oauth_callback)
    return app


async def start_server(bot, host: str = "0.0.0.0", port: int = 8080) -> web.AppRunner:
    app = create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    return runner
