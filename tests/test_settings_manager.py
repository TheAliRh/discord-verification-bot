import pytest


async def test_new_guild_gets_defaults(settings_manager_instance):
    settings = await settings_manager_instance.get(111)
    assert settings["method"] == "button"
    assert settings["verified_role_id"] is None
    assert settings["min_account_age_days"] == 0


async def test_partial_update_preserves_other_defaults(settings_manager_instance):
    updated = await settings_manager_instance.update(111, {"method": "captcha"})
    assert updated["method"] == "captcha"
    assert updated["max_attempts"] == 3  # untouched default preserved


async def test_nested_deep_merge(settings_manager_instance):
    updated = await settings_manager_instance.update(
        111, {"method_settings": {"captcha": {"length": 8}}}
    )
    assert updated["method_settings"]["captcha"]["length"] == 8
    assert updated["method_settings"]["captcha"]["type"] == "alphanumeric"  # untouched


async def test_persists_across_manager_restart(tmp_path):
    """Simulates a bot restart: a fresh SettingsManager instance still sees prior writes."""
    import settings.manager as manager_module
    from settings.manager import SettingsManager

    original_path = manager_module.DB_PATH
    manager_module.DB_PATH = tmp_path / "restart_test.db"
    try:
        sm1 = SettingsManager()
        await sm1.init()
        await sm1.update(222, {"method": "email"})
        await sm1.close()

        sm2 = SettingsManager()
        await sm2.init()
        reloaded = await sm2.get(222)
        assert reloaded["method"] == "email"
        await sm2.close()
    finally:
        manager_module.DB_PATH = original_path


async def test_reset_reverts_to_defaults(settings_manager_instance):
    await settings_manager_instance.update(111, {"method": "phone"})
    reset_settings = await settings_manager_instance.reset(111)
    assert reset_settings["method"] == "button"

    reloaded = await settings_manager_instance.get(111)
    assert reloaded["method"] == "button"


async def test_cache_hit_returns_same_object_without_db_hit(settings_manager_instance):
    first = await settings_manager_instance.get(333)
    # Corrupt the DB connection to prove the second get() doesn't touch it
    settings_manager_instance._db = None
    second = await settings_manager_instance.get(
        333
    )  # should come from cache, not crash
    assert first == second
