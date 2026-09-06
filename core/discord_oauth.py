"""
Minimal Discord OAuth2 client.

Three responsibilities: build the authorize URL a user's browser is sent
to, exchange the code Discord returns for an access token, and fetch the
authorizing user's identity so we can confirm it matches who clicked Verify.

Credentials are read fresh from os.environ on every call rather than cached
as module-level constants at import time - see core/email_sender.py's
docstring for why that matters (import-order fragility).
"""

import os
from typing import Any
from urllib.parse import urlencode

import aiohttp

_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
_TOKEN_URL = "https://discord.com/api/oauth2/token"
_USER_URL = "https://discord.com/api/users/@me"


class OAuthNotConfigured(Exception):
    """Raised when DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET are missing from .env."""


def is_configured() -> bool:
    return all([os.getenv("DISCORD_CLIENT_ID"), os.getenv("DISCORD_CLIENT_SECRET")])


def build_authorize_url(state: str) -> str:
    if not is_configured():
        raise OAuthNotConfigured(
            "DISCORD_CLIENT_ID / DISCORD_CLIENT_SECRET are not set in .env"
        )

    redirect_uri = os.getenv(
        "OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback"
    )
    params = {
        "client_id": os.getenv("DISCORD_CLIENT_ID"),
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    }
    return f"{_AUTHORIZE_URL}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> str:
    redirect_uri = os.getenv(
        "OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback"
    )
    data = {
        "client_id": os.getenv("DISCORD_CLIENT_ID"),
        "client_secret": os.getenv("DISCORD_CLIENT_SECRET"),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    async with aiohttp.ClientSession() as session:
        async with session.post(_TOKEN_URL, data=data, headers=headers) as resp:
            resp.raise_for_status()
            payload: dict[str, Any] = await resp.json()
            return str(payload["access_token"])


async def fetch_discord_user(access_token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        async with session.get(_USER_URL, headers=headers) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json()
            return data
