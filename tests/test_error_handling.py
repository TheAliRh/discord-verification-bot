import pytest


class _BrokenExecute:
    """
    Mimics aiosqlite's execute() return value closely enough for these tests:
    real aiosqlite Cursor objects work BOTH as `await db.execute(...)` (used
    by update()/reset()) and `async with db.execute(...) as cursor` (used by
    get()). A plain async function only supports the first form correctly.
    """

    def __init__(self, error):
        self._error = error

    def __await__(self):
        async def _raise():
            raise self._error

        return _raise().__await__()

    async def __aenter__(self):
        raise self._error

    async def __aexit__(self, *args):
        return False


def _broken_execute_factory(error):
    def _execute(*args, **kwargs):
        return _BrokenExecute(error)

    return _execute


# --- settings/manager.py: get() degrades gracefully on DB failure ---


async def test_get_fails_closed_on_db_read_failure(
    settings_manager_instance, monkeypatch
):
    monkeypatch.setattr(
        settings_manager_instance._db,
        "execute",
        _broken_execute_factory(RuntimeError("simulated disk failure")),
    )

    settings = await settings_manager_instance.get(999)  # should not raise
    assert settings["enabled"] is False  # fails CLOSED, not just "defaults"
    assert (
        settings["method"] == "button"
    )  # base is still DEFAULT_SETTINGS, just disabled


async def test_get_fails_closed_on_corrupted_json(settings_manager_instance):
    # Insert a row with invalid JSON directly, bypassing update()'s normal path
    await settings_manager_instance._db.execute(
        "INSERT INTO guild_config (guild_id, config_json) VALUES (?, ?)",
        (555, "{not valid json"),
    )
    await settings_manager_instance._db.commit()

    settings = await settings_manager_instance.get(555)  # should not raise
    assert settings["enabled"] is False
    assert settings["method"] == "button"


async def test_db_error_never_downgrades_a_strict_configuration_to_an_easier_one(
    settings_manager_instance, monkeypatch
):
    """
    The exact scenario being fixed: a guild that deliberately configured a
    strict setup (email verification, a high minimum account age,
    kick_on_fail) must NOT be silently downgraded to a bare, trivially
    bypassable button just because a DB read happened to fail. Verification
    must be blocked entirely (enabled=False) instead - a hard stop is far
    safer than quietly serving the easiest possible method during an outage,
    which could coincide with exactly the kind of load spike a raid causes.
    """
    strict_settings = {
        "method": "email",
        "min_account_age_days": 30,
        "max_attempts": 1,
        "kick_on_fail": True,
    }
    await settings_manager_instance.update(777, strict_settings)

    # Simulate the cache being cold (as if the bot just restarted) and the
    # subsequent DB read failing, so get() has no choice but to hit the DB.
    settings_manager_instance._cache.pop(777, None)
    monkeypatch.setattr(
        settings_manager_instance._db,
        "execute",
        _broken_execute_factory(RuntimeError("simulated disk failure")),
    )

    settings = await settings_manager_instance.get(777)

    assert settings["enabled"] is False  # verification blocked outright
    # Specifically confirm it did NOT silently serve the easy defaults
    # while claiming to still be "enabled" - that combination is exactly
    # the dangerous one this fix closes.
    if settings["method"] == "button":
        assert settings["enabled"] is False, (
            "DB error served the easiest method (button) while still enabled - "
            "this is the exact fail-open regression being fixed."
        )


async def test_new_guild_with_no_row_still_gets_real_open_defaults(
    settings_manager_instance,
):
    """
    The other half of the distinction: a guild that never configured
    anything is NOT a failure - it's a legitimate fresh state, and must
    still get real, usable (enabled=True) defaults so the bot works out of
    the box, per the very first design goal from settings/defaults.py.
    """
    settings = await settings_manager_instance.get(
        888
    )  # no row exists, no error either
    assert settings["enabled"] is True
    assert settings["method"] == "button"


# --- settings/manager.py: update()/reset() raise clearly instead of silently "succeeding" ---


async def test_update_raises_persistence_error_on_db_write_failure(
    settings_manager_instance, monkeypatch
):
    from settings.manager import SettingsPersistenceError

    monkeypatch.setattr(
        settings_manager_instance._db,
        "execute",
        _broken_execute_factory(RuntimeError("simulated write failure")),
    )

    with pytest.raises(SettingsPersistenceError):
        await settings_manager_instance.update(1, {"method": "captcha"})


async def test_update_failure_does_not_corrupt_the_cache(
    settings_manager_instance, monkeypatch
):
    """A failed write must not update the in-memory cache - that would make it LOOK saved when it wasn't."""
    from settings.manager import SettingsPersistenceError

    await settings_manager_instance.update(
        1, {"method": "email"}
    )  # succeeds normally first

    monkeypatch.setattr(
        settings_manager_instance._db,
        "execute",
        _broken_execute_factory(RuntimeError("simulated write failure")),
    )

    with pytest.raises(SettingsPersistenceError):
        await settings_manager_instance.update(1, {"method": "phone"})

    # Cache should still reflect the last successful write, not the failed one
    settings = await settings_manager_instance.get(1)
    assert settings["method"] == "email"


async def test_reset_raises_persistence_error_on_db_write_failure(
    settings_manager_instance, monkeypatch
):
    from settings.manager import SettingsPersistenceError

    monkeypatch.setattr(
        settings_manager_instance._db,
        "execute",
        _broken_execute_factory(RuntimeError("simulated delete failure")),
    )

    with pytest.raises(SettingsPersistenceError):
        await settings_manager_instance.reset(1)


# --- core/logging_config.py: graceful degradation if the log directory can't be created ---


def test_setup_logging_falls_back_to_console_only_if_log_dir_fails(monkeypatch):
    import logging
    from core import logging_config

    class _FakeLogDir:
        def mkdir(self, *args, **kwargs):
            raise OSError("simulated read-only filesystem")

    monkeypatch.setattr(logging_config, "LOG_DIR", _FakeLogDir())

    logging_config.setup_logging()  # should not raise

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 1  # console only, file handler was skipped
    assert isinstance(root_logger.handlers[0], logging.StreamHandler)


def test_setup_logging_normally_has_two_handlers(tmp_path, monkeypatch):
    import logging
    from core import logging_config

    monkeypatch.setattr(logging_config, "LOG_DIR", tmp_path / "logs")
    monkeypatch.setattr(logging_config, "LOG_FILE", tmp_path / "logs" / "bot.log")

    logging_config.setup_logging()

    root_logger = logging.getLogger()
    assert len(root_logger.handlers) == 2  # console + file, working normally


# --- web/server.py: unexpected role-granting failure returns a styled page, not a raw 500 ---


async def test_oauth_callback_handles_unexpected_grant_failure(
    settings_manager_instance, monkeypatch
):
    import aiohttp
    from aiohttp import web
    from unittest.mock import AsyncMock, patch
    import web.server as server_module
    from core.oauth_state import create_state

    monkeypatch.setattr(server_module, "settings_manager", settings_manager_instance)
    await settings_manager_instance.update(777, {"verified_role_id": 100})

    class FakeBot:
        def get_guild(self, gid):
            raise RuntimeError("simulated unexpected failure deep in discord.py")

    app = server_module.create_app(FakeBot())
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 8199)
    await site.start()

    try:
        state = create_state(guild_id=777, user_id=888)
        with (
            patch.object(
                server_module, "exchange_code_for_token", AsyncMock(return_value="tok")
            ),
            patch.object(
                server_module,
                "fetch_discord_user",
                AsyncMock(return_value={"id": "888"}),
            ),
        ):
            async with aiohttp.ClientSession() as client:
                async with client.get(
                    f"http://127.0.0.1:8199/oauth/callback?code=c&state={state}"
                ) as resp:
                    assert resp.status == 500
                    text = await resp.text()
                    assert "contact a server admin" in text.lower()
    finally:
        await runner.cleanup()


async def test_fail_closed_settings_actually_block_verification_end_to_end(
    settings_manager_instance, monkeypatch
):
    """
    Not just that the returned dict LOOKS disabled - confirm it actually
    blocks a real verification attempt through the same shared gate every
    module goes through, since that's what actually matters.
    """
    from core.prechecks import passes_prechecks
    from tests.conftest import FakeInteraction, FakeMember, FakeGuild

    monkeypatch.setattr(
        settings_manager_instance._db,
        "execute",
        _broken_execute_factory(RuntimeError("simulated disk failure")),
    )

    guild_settings = await settings_manager_instance.get(999)  # fails closed

    interaction = FakeInteraction(
        user=FakeMember(user_id=1), guild=FakeGuild(guild_id=999)
    )
    result = await passes_prechecks(interaction, guild_settings)

    assert result is False
    assert "turned off" in interaction.response.sent[0].lower()
