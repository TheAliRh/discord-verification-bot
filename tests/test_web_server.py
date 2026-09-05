from unittest.mock import AsyncMock, patch

import aiohttp
from aiohttp import web
import pytest

import web.server as server_module
from core.oauth_state import create_state
from tests.conftest import FakeRole, FakeMember, FakeGuild


class FakeBot:
    def __init__(self, guild):
        self._guild = guild

    def get_guild(self, gid):
        return self._guild


@pytest.fixture
async def running_server(settings_manager_instance, monkeypatch):
    """Starts a real local server on a fixed test port, backed by a real (throwaway) SettingsManager."""
    import settings as settings_pkg

    monkeypatch.setattr(settings_pkg, "settings_manager", settings_manager_instance)
    monkeypatch.setattr(server_module, "settings_manager", settings_manager_instance)

    verified_role = FakeRole(555)
    member = FakeMember(user_id=888)
    guild = FakeGuild(guild_id=777, roles=[verified_role], member=member)
    bot = FakeBot(guild)

    await settings_manager_instance.update(777, {"verified_role_id": 555})

    app = server_module.create_app(bot)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8123)
    await site.start()

    yield "http://127.0.0.1:8123", member

    await runner.cleanup()


async def test_missing_code_and_state_returns_400(running_server):
    base_url, _ = running_server
    async with aiohttp.ClientSession() as client:
        async with client.get(f"{base_url}/oauth/callback") as resp:
            assert resp.status == 400


async def test_invalid_state_token_returns_400(running_server):
    base_url, _ = running_server
    async with aiohttp.ClientSession() as client:
        async with client.get(
            f"{base_url}/oauth/callback?code=abc&state=bogus"
        ) as resp:
            assert resp.status == 400
            text = await resp.text()
            assert "expired" in text.lower()


async def test_full_flow_with_matching_identity_grants_role(running_server):
    base_url, member = running_server
    state = create_state(guild_id=777, user_id=888)

    with (
        patch.object(
            server_module,
            "exchange_code_for_token",
            AsyncMock(return_value="fake-token"),
        ),
        patch.object(
            server_module,
            "fetch_discord_user",
            AsyncMock(return_value={"id": "888", "username": "tester"}),
        ),
    ):
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"{base_url}/oauth/callback?code=real-code&state={state}"
            ) as resp:
                assert resp.status == 200
                text = await resp.text()
                assert "verified" in text.lower()

    assert 555 in member.added_roles


async def test_identity_mismatch_returns_403(running_server):
    base_url, member = running_server
    state = create_state(guild_id=777, user_id=888)

    with (
        patch.object(
            server_module,
            "exchange_code_for_token",
            AsyncMock(return_value="fake-token"),
        ),
        patch.object(
            server_module,
            "fetch_discord_user",
            AsyncMock(return_value={"id": "999", "username": "someone-else"}),
        ),
    ):
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"{base_url}/oauth/callback?code=real-code&state={state}"
            ) as resp:
                assert resp.status == 403
                text = await resp.text()
                assert "mismatch" in text.lower()

    assert 555 not in member.added_roles


async def test_replaying_consumed_state_is_rejected(running_server):
    base_url, _ = running_server
    state = create_state(guild_id=777, user_id=888)

    with (
        patch.object(
            server_module,
            "exchange_code_for_token",
            AsyncMock(return_value="fake-token"),
        ),
        patch.object(
            server_module,
            "fetch_discord_user",
            AsyncMock(return_value={"id": "888", "username": "tester"}),
        ),
    ):
        async with aiohttp.ClientSession() as client:
            async with client.get(
                f"{base_url}/oauth/callback?code=real-code&state={state}"
            ) as resp:
                assert resp.status == 200

            async with client.get(
                f"{base_url}/oauth/callback?code=real-code&state={state}"
            ) as resp:
                assert resp.status == 400
