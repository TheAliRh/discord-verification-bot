from modules.captcha import CaptchaButton, CaptchaModal, CaptchaVerificationView
from tests.conftest import FakeRole, FakeMember, FakeGuild, FakeInteraction


DEFAULT_SETTINGS = {
    "verified_role_id": 100,
    "min_account_age_days": 0,
    "method_settings": {"captcha": {"length": 6, "type": "alphanumeric"}},
}


async def test_click_opens_modal_with_code_in_label(monkeypatch):
    import settings as settings_pkg

    interaction = FakeInteraction()

    async def fake_get(guild_id):
        return DEFAULT_SETTINGS

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = CaptchaButton()
    await button.callback(interaction)

    assert len(interaction.response.sent) == 1
    modal = interaction.response.sent[0]
    assert isinstance(modal, CaptchaModal)
    assert "Type this code:" in modal.answer.label


async def test_click_blocked_by_precheck_does_not_open_modal(monkeypatch):
    import settings as settings_pkg

    member = FakeMember(user_id=1, created_days_ago=1)
    interaction = FakeInteraction(user=member)
    settings_with_age_check = {**DEFAULT_SETTINGS, "min_account_age_days": 7}

    async def fake_get(guild_id):
        return settings_with_age_check

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = CaptchaButton()
    await button.callback(interaction)

    assert len(interaction.response.sent) == 1
    assert not isinstance(
        interaction.response.sent[0], CaptchaModal
    )  # message, not a modal


async def test_correct_code_grants_verification():
    from core.challenge_store import store_challenge

    verified_role = FakeRole(100)
    guild = FakeGuild(roles=[verified_role])
    interaction = FakeInteraction(guild=guild)
    store_challenge(interaction.user.id, "ABC234")

    modal = CaptchaModal(expected_code="ABC234", settings={"verified_role_id": 100})
    modal.answer._value = "ABC234"
    await modal.on_submit(interaction)

    assert 100 in interaction.user.added_roles


async def test_wrong_code_denies_verification():
    guild = FakeGuild()
    interaction = FakeInteraction(guild=guild)

    modal = CaptchaModal(expected_code="ABC234", settings={"verified_role_id": 100})
    modal.answer._value = "WRONGCODE"
    await modal.on_submit(interaction)

    assert interaction.user.added_roles == []
    assert interaction.response.sent[0].startswith("❌")


def test_view_has_static_custom_id_and_is_persistent():
    view = CaptchaVerificationView()
    assert view.timeout is None
    assert view.children[0].custom_id == "verify:captcha:click"
