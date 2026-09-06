"""
Tests for bot.py's event handlers.

Importing bot.py constructs a real discord.py Bot instance, but that's
synchronous and makes no network calls - the earlier issue that looked like
a hang was actually an unrelated bug (a bare `discord.Forbidden(response=None)`
in an older ad-hoc test script, not this import). Confirmed safe to import
directly here.
"""

import discord
from discord import app_commands
import pytest

from tests.conftest import FakeRole, FakeMember, FakeGuild


@pytest.fixture
async def bot_module(tmp_path, monkeypatch):
    import settings.manager as manager_module

    monkeypatch.setattr(manager_module, "DB_PATH", tmp_path / "bot_events_test.db")

    import bot as bot_mod

    yield bot_mod

    # bot.py is cached in sys.modules, so bot_mod.settings_manager is the SAME
    # singleton across every test in this file. Without closing it here, each
    # test's settings_manager.init() call leaks another open aiosqlite
    # connection (and its backing thread) without ever releasing the last one.
    await bot_mod.settings_manager.close()
    bot_mod.settings_manager._db = None
    bot_mod.settings_manager._cache.clear()


async def test_on_member_join_assigns_unverified_role_and_dms(bot_module):
    unverified_role = FakeRole(500)
    guild = FakeGuild(guild_id=1001, roles=[unverified_role])
    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(
        1001, {"unverified_role_id": 500, "verify_channel_id": 777}
    )

    member = FakeMember(user_id=1)
    member.guild = guild

    await bot_module.bot.on_member_join(member)

    assert 500 in member.added_roles
    assert len(member.dms_sent) == 1
    assert "<#777>" in member.dms_sent[0]


async def test_on_member_join_no_unverified_role_configured(bot_module):
    guild = FakeGuild(guild_id=1002)
    await bot_module.settings_manager.init()

    member = FakeMember(user_id=2)
    member.guild = guild

    await bot_module.bot.on_member_join(member)

    assert member.added_roles == []
    assert len(member.dms_sent) == 1
    assert "the verification channel" in member.dms_sent[0]


async def test_on_member_join_dms_closed_does_not_crash(bot_module):
    unverified_role = FakeRole(500)
    guild = FakeGuild(guild_id=1003, roles=[unverified_role])
    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(1003, {"unverified_role_id": 500})

    member = FakeMember(user_id=3)
    member.guild = guild
    member.dm_forbidden = True

    await bot_module.bot.on_member_join(member)  # should not raise

    assert 500 in member.added_roles
    assert member.dms_sent == []


async def test_on_member_join_missing_configured_role_does_not_crash(bot_module):
    guild = FakeGuild(guild_id=1004, roles=[])  # role 999 doesn't exist here
    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(1004, {"unverified_role_id": 999})

    member = FakeMember(user_id=4)
    member.guild = guild

    await bot_module.bot.on_member_join(member)  # should not raise

    assert member.added_roles == []
    assert len(member.dms_sent) == 1  # DM still attempted despite the role issue


async def test_on_member_join_disabled_skips_everything(bot_module):
    unverified_role = FakeRole(500)
    guild = FakeGuild(guild_id=1005, roles=[unverified_role])
    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(
        1005, {"unverified_role_id": 500, "enabled": False}
    )

    member = FakeMember(user_id=5)
    member.guild = guild

    await bot_module.bot.on_member_join(member)

    assert member.added_roles == []
    assert member.dms_sent == []


# --- Global app command error handler ---


class _FakeCommand:
    name = "verify-view"


class _FakeErrorInteraction:
    def __init__(self):
        from tests.conftest import FakeResponse

        self.response = FakeResponse()
        self.command = _FakeCommand()


async def test_missing_permissions_gives_clear_message(bot_module):
    interaction = _FakeErrorInteraction()
    error = app_commands.MissingPermissions(["manage_guild"])

    await bot_module.on_app_command_error(interaction, error)

    assert "Manage Server" in interaction.response.sent[0]


async def test_no_private_message_gives_clear_message(bot_module):
    interaction = _FakeErrorInteraction()
    error = app_commands.NoPrivateMessage()

    await bot_module.on_app_command_error(interaction, error)

    assert "server" in interaction.response.sent[0].lower()


async def test_unexpected_error_falls_back_to_generic_message(bot_module):
    interaction = _FakeErrorInteraction()
    error = RuntimeError("something exploded")

    await bot_module.on_app_command_error(interaction, error)  # should not raise

    assert "went wrong" in interaction.response.sent[0].lower()


# --- setup_hook() vs on_ready(): one-time init must not repeat on reconnect ---


async def test_setup_hook_initializes_db_registers_views_and_syncs_commands(
    bot_module, monkeypatch
):
    from unittest.mock import AsyncMock
    from modules import MODULES

    fake_start_server = AsyncMock(return_value="fake-runner")
    monkeypatch.setattr(bot_module, "start_server", fake_start_server)
    monkeypatch.setattr(bot_module.bot.tree, "sync", AsyncMock())

    add_view_calls = []
    monkeypatch.setattr(
        bot_module.bot, "add_view", lambda view: add_view_calls.append(view)
    )

    await bot_module.bot.setup_hook()

    assert (
        bot_module.settings_manager._db is not None
    )  # real DB connection was actually opened
    assert len(add_view_calls) == len(
        MODULES
    )  # one persistent view registered per module
    bot_module.bot.tree.sync.assert_awaited_once()
    fake_start_server.assert_awaited_once()


async def test_on_ready_does_not_reinitialize_anything(bot_module, monkeypatch):
    """
    Regression test: on_ready() can fire multiple times per process (discord.py
    calls it again after a dropped gateway connection reconnects). It must NOT
    touch settings_manager.init(), add_view(), or tree.sync() - all one-time
    setup belongs in setup_hook(), which discord.py guarantees runs only once.
    """
    from unittest.mock import AsyncMock

    fake_init = AsyncMock()
    monkeypatch.setattr(bot_module.settings_manager, "init", fake_init)
    monkeypatch.setattr(bot_module.bot.tree, "sync", AsyncMock())
    add_view_calls = []
    monkeypatch.setattr(
        bot_module.bot, "add_view", lambda view: add_view_calls.append(view)
    )

    # Simulate on_ready firing three times, as it could across reconnects
    await bot_module.bot.on_ready()
    await bot_module.bot.on_ready()
    await bot_module.bot.on_ready()

    fake_init.assert_not_awaited()
    bot_module.bot.tree.sync.assert_not_awaited()
    assert add_view_calls == []


# --- /verify-post: uses the configured verification channel, and never crashes on bad data ---


class _FakeChannel(discord.abc.Messageable):
    """A real discord.abc.Messageable subclass - required so verify_post's
    isinstance(channel, discord.abc.Messageable) check actually passes."""

    def __init__(self, channel_id: int):
        self.id = channel_id
        self.mention = f"<#{channel_id}>"
        self.sent: list[dict] = []

    async def _get_channel(self):
        return self

    async def send(self, embed=None, view=None, **kwargs):
        self.sent.append({"embed": embed, "view": view})


class _NonMessageableChannel:
    """A channel type that exists but can't be posted to (e.g. a CategoryChannel) -
    deliberately NOT a Messageable subclass, so the isinstance check correctly fails."""

    def __init__(self, channel_id: int):
        self.id = channel_id


async def test_verify_post_uses_configured_channel_not_current_channel(bot_module):
    from tests.conftest import FakeGuild, FakeRole

    configured_channel = _FakeChannel(channel_id=555)
    current_channel = _FakeChannel(
        channel_id=999
    )  # where the command was run - should NOT be used

    guild = FakeGuild(guild_id=1, roles=[FakeRole(100)])
    guild.get_channel = lambda cid: configured_channel if cid == 555 else None

    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(
        1, {"verified_role_id": 100, "verify_channel_id": 555, "method": "button"}
    )

    interaction = _make_command_interaction(guild, current_channel)
    await bot_module.verify_post.callback(interaction)

    assert len(configured_channel.sent) == 1
    assert len(current_channel.sent) == 0
    assert (
        "555" in interaction.response.sent[0]
        or "<#555>" in interaction.response.sent[0]
    )


async def test_verify_post_falls_back_when_configured_channel_deleted(bot_module):
    from tests.conftest import FakeGuild, FakeRole

    current_channel = _FakeChannel(channel_id=999)
    guild = FakeGuild(guild_id=2, roles=[FakeRole(100)])
    guild.get_channel = lambda cid: None  # configured channel (555) no longer exists

    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(
        2, {"verified_role_id": 100, "verify_channel_id": 555, "method": "button"}
    )

    interaction = _make_command_interaction(guild, current_channel)
    await bot_module.verify_post.callback(interaction)

    assert len(current_channel.sent) == 1  # fell back to current channel
    assert "no longer exists" in interaction.response.sent[0]


async def test_verify_post_falls_back_when_configured_channel_not_messageable(
    bot_module,
):
    from tests.conftest import FakeGuild, FakeRole

    current_channel = _FakeChannel(channel_id=999)
    non_messageable = _NonMessageableChannel(channel_id=555)
    guild = FakeGuild(guild_id=3, roles=[FakeRole(100)])
    guild.get_channel = lambda cid: non_messageable if cid == 555 else None

    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(
        3, {"verified_role_id": 100, "verify_channel_id": 555, "method": "button"}
    )

    interaction = _make_command_interaction(guild, current_channel)
    await bot_module.verify_post.callback(interaction)

    assert len(current_channel.sent) == 1
    assert "isn't a channel type" in interaction.response.sent[0]


async def test_verify_post_does_not_crash_on_invalid_stored_method(bot_module):
    """
    Regression test: guild_settings["method"] could be a stale/invalid value
    (e.g. a method removed in an update). This must NOT raise KeyError -
    get_module() falls back to Button, and the embed footer must use that
    same resolved module instead of re-indexing MODULES directly.
    """
    from tests.conftest import FakeGuild, FakeRole

    channel = _FakeChannel(channel_id=999)
    guild = FakeGuild(guild_id=4, roles=[FakeRole(100)])
    guild.get_channel = lambda cid: None

    await bot_module.settings_manager.init()
    await bot_module.settings_manager.update(
        4, {"verified_role_id": 100, "method": "this_method_does_not_exist"}
    )

    interaction = _make_command_interaction(guild, channel)
    await bot_module.verify_post.callback(interaction)  # must not raise KeyError

    assert len(channel.sent) == 1
    embed = channel.sent[0]["embed"]
    assert "Button" in embed.footer.text  # fell back to Button's display name


def _make_command_interaction(guild, channel):
    from tests.conftest import FakeMember, FakeResponse

    class _Interaction:
        def __init__(self):
            self.guild = guild
            self.guild_id = guild.id
            self.channel = channel
            self.user = FakeMember(user_id=1)
            self.response = FakeResponse()

    return _Interaction()
