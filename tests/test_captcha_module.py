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
    store_challenge(interaction.guild_id, interaction.user.id, "ABC234")

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


async def test_same_user_verifying_in_two_guilds_does_not_cross_contaminate(
    monkeypatch,
):
    """
    Integration-level regression test for the cross-guild challenge bug:
    the same user clicking Verify in two different guilds must get two
    independent codes, and Guild A's code must not work when submitted
    against Guild B's challenge (or vice versa).
    """
    import settings as settings_pkg

    guild_a = FakeGuild(guild_id=100, roles=[FakeRole(1)])
    guild_b = FakeGuild(guild_id=200, roles=[FakeRole(2)])
    same_user = FakeMember(user_id=42)

    settings_by_guild = {
        100: {
            "verified_role_id": 1,
            "min_account_age_days": 0,
            "method_settings": {"captcha": {"length": 6, "type": "alphanumeric"}},
        },
        200: {
            "verified_role_id": 2,
            "min_account_age_days": 0,
            "method_settings": {"captcha": {"length": 6, "type": "alphanumeric"}},
        },
    }

    async def fake_get(guild_id):
        return settings_by_guild[guild_id]

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    # Click Verify in Guild A -> get a modal with Guild A's code
    interaction_a = FakeInteraction(user=same_user, guild=guild_a)
    button_a = CaptchaButton()
    await button_a.callback(interaction_a)
    modal_a = interaction_a.response.sent[0]
    code_a = modal_a.answer.label.split(": ")[1]

    # Same user clicks Verify in Guild B BEFORE finishing Guild A's -> gets Guild B's code
    interaction_b = FakeInteraction(user=same_user, guild=guild_b)
    button_b = CaptchaButton()
    await button_b.callback(interaction_b)
    modal_b = interaction_b.response.sent[0]
    code_b = modal_b.answer.label.split(": ")[1]

    assert (
        code_a != code_b
    )  # two independent codes were generated, not one overwriting the other

    # Submitting Guild A's code in Guild B's modal must fail
    modal_b.answer._value = code_a
    wrong_guild_interaction = FakeInteraction(user=same_user, guild=guild_b)
    await modal_b.on_submit(wrong_guild_interaction)
    assert wrong_guild_interaction.user.added_roles == []  # not granted

    # Submitting Guild A's own code in Guild A's own modal must still succeed
    modal_a.answer._value = code_a
    correct_interaction = FakeInteraction(user=same_user, guild=guild_a)
    await modal_a.on_submit(correct_interaction)
    assert 1 in correct_interaction.user.added_roles  # Guild A's role granted correctly
