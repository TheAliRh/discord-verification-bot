from unittest.mock import patch

from modules.button import VerifyButton, ButtonVerificationView
from tests.conftest import FakeRole, FakeMember, FakeGuild, FakeInteraction


async def test_click_grants_role_when_precheck_passes(monkeypatch):
    import settings as settings_pkg

    verified_role = FakeRole(100)
    guild = FakeGuild(roles=[verified_role])
    member = FakeMember(user_id=1, created_days_ago=365)
    interaction = FakeInteraction(user=member, guild=guild)

    async def fake_get(guild_id):
        return {"verified_role_id": 100, "min_account_age_days": 0}

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = VerifyButton()
    await button.callback(interaction)

    assert 100 in member.added_roles
    assert interaction.response.sent[0].startswith("✅")


async def test_click_blocked_by_precheck_does_not_grant(monkeypatch):
    import settings as settings_pkg

    verified_role = FakeRole(100)
    guild = FakeGuild(roles=[verified_role])
    member = FakeMember(user_id=1, created_days_ago=1)  # too new
    interaction = FakeInteraction(user=member, guild=guild)

    async def fake_get(guild_id):
        return {"verified_role_id": 100, "min_account_age_days": 7}

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = VerifyButton()
    await button.callback(interaction)

    assert member.added_roles == []
    assert "day" in interaction.response.sent[0].lower()


def test_view_has_static_custom_id_and_is_persistent():
    view = ButtonVerificationView()
    assert view.timeout is None
    assert view.children[0].custom_id == "verify:button:click"
