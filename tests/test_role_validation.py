from core.role_validation import validate_assignable_role
from tests.conftest import FakeRole, FakeGuild


def test_normal_role_below_bot_is_accepted():
    guild = FakeGuild()  # default: bot has manage_roles, top_role id 999999
    role = FakeRole(100)
    assert validate_assignable_role(guild, role) is None


def test_everyone_role_is_rejected():
    guild = FakeGuild()
    everyone_role = FakeRole(guild.id, is_default=True)
    reason = validate_assignable_role(guild, everyone_role)
    assert reason is not None
    assert "@everyone" in reason


def test_managed_role_is_rejected():
    guild = FakeGuild()
    bot_integration_role = FakeRole(200, managed=True)
    reason = validate_assignable_role(guild, bot_integration_role)
    assert reason is not None
    assert "managed by an integration" in reason


def test_role_missing_manage_roles_permission_is_rejected():
    from types import SimpleNamespace

    guild = FakeGuild()
    guild.me = SimpleNamespace(
        top_role=FakeRole(999999),
        guild_permissions=SimpleNamespace(manage_roles=False),
    )
    role = FakeRole(100)
    reason = validate_assignable_role(guild, role)
    assert reason is not None
    assert "Manage Roles" in reason


def test_role_at_or_above_bots_top_role_is_rejected():
    from types import SimpleNamespace

    guild = FakeGuild()
    guild.me = SimpleNamespace(
        top_role=FakeRole(50),
        guild_permissions=SimpleNamespace(manage_roles=True),
    )
    role_above = FakeRole(100)  # id 100 >= bot's top_role id 50
    reason = validate_assignable_role(guild, role_above)
    assert reason is not None
    assert "isn't above" in reason


def test_managed_role_rejected_even_if_hierarchy_and_permission_are_fine():
    """Managed status must be checked independently - being below the bot's role doesn't make it assignable."""
    guild = FakeGuild()  # bot has manage_roles and a very high top_role
    managed_role = FakeRole(
        1, managed=True
    )  # well below the bot's role, but still managed
    reason = validate_assignable_role(guild, managed_role)
    assert reason is not None
    assert "managed by an integration" in reason


def test_everyone_rejected_even_if_it_would_otherwise_pass_hierarchy():
    """@everyone always has the lowest position, so this also confirms is_default() is checked, not just position."""
    guild = FakeGuild()
    everyone_role = FakeRole(guild.id, is_default=True)
    reason = validate_assignable_role(guild, everyone_role)
    assert reason is not None
    assert "@everyone" in reason
