from types import SimpleNamespace

from ui.setup_wizard import (
    SetupView,
    MethodSelect,
    VerifiedRoleSelect,
    VerifyChannelSelect,
    EditWelcomeMessageButton,
    FinishSetupButton,
    CancelSetupButton,
    WelcomeMessageModal,
)
from tests.conftest import FakeRole, FakeGuild, FakeInteraction


def _guild_with_bot_role_above(top_role_id=999):
    """A guild where the bot's own top role sits above anything picked in these tests."""
    guild = FakeGuild()
    guild.me = SimpleNamespace(top_role=FakeRole(top_role_id))
    return guild


# --- SetupView construction ---


def test_defaults_from_empty_settings():
    view = SetupView({})
    assert view.method == "button"
    assert view.verified_role_id is None
    assert view.verify_channel_id is None
    assert "Click below" in view.welcome_message


def test_loads_existing_settings():
    existing = {
        "method": "image_captcha",
        "verified_role_id": 123456,
        "verify_channel_id": 789012,
        "welcome_message": "Custom hello!",
    }
    view = SetupView(existing)
    assert view.method == "image_captcha"
    assert view.verified_role_id == 123456
    assert view.verify_channel_id == 789012
    assert view.welcome_message == "Custom hello!"


def test_embed_shows_not_set_for_unset_fields():
    view = SetupView({})
    embed = view.build_embed()
    role_field = next(f for f in embed.fields if f.name == "Verified role")
    channel_field = next(f for f in embed.fields if f.name == "Verify channel")
    assert role_field.value == "*not set*"
    assert channel_field.value == "*not set*"


def test_embed_shows_mentions_once_set():
    view = SetupView({"verified_role_id": 111, "verify_channel_id": 222})
    embed = view.build_embed()
    role_field = next(f for f in embed.fields if f.name == "Verified role")
    channel_field = next(f for f in embed.fields if f.name == "Verify channel")
    assert role_field.value == "<@&111>"
    assert channel_field.value == "<#222>"


def test_all_expected_components_present():
    view = SetupView({})
    component_types = {type(c).__name__ for c in view.children}
    assert component_types == {
        "MethodSelect",
        "VerifiedRoleSelect",
        "VerifyChannelSelect",
        "EditWelcomeMessageButton",
        "FinishSetupButton",
        "CancelSetupButton",
    }


def test_wizard_is_not_persistent():
    view = SetupView({})
    assert view.timeout == 300  # session-only, unlike the verification message views


# --- MethodSelect ---


async def test_method_select_updates_wizard_state():
    view = SetupView({})
    select = view.children[0]
    assert isinstance(select, MethodSelect)
    select._values = ["captcha"]

    interaction = FakeInteraction()
    await select.callback(interaction)

    assert view.method == "captcha"
    assert interaction.response._done is True  # edit_message was called


# --- VerifiedRoleSelect ---


async def test_role_select_updates_wizard_state_when_hierarchy_ok():
    view = SetupView({})
    select = next(c for c in view.children if isinstance(c, VerifiedRoleSelect))

    picked_role = FakeRole(50)  # below the bot's top role (999)
    select._values = [picked_role]
    guild = _guild_with_bot_role_above(top_role_id=999)
    interaction = FakeInteraction(guild=guild)

    await select.callback(interaction)

    assert view.verified_role_id == 50


async def test_role_select_rejects_role_at_or_above_bot():
    view = SetupView({})
    select = next(c for c in view.children if isinstance(c, VerifiedRoleSelect))

    picked_role = FakeRole(9999)  # at/above the bot's own top role (999)
    select._values = [picked_role]
    guild = _guild_with_bot_role_above(top_role_id=999)
    interaction = FakeInteraction(guild=guild)

    await select.callback(interaction)

    assert view.verified_role_id is None  # rejected, not saved
    assert "isn't above" in interaction.response.sent[0]


# --- VerifyChannelSelect ---


async def test_channel_select_updates_wizard_state():
    view = SetupView({})
    select = next(c for c in view.children if isinstance(c, VerifyChannelSelect))

    fake_channel = SimpleNamespace(id=555)
    select._values = [fake_channel]
    interaction = FakeInteraction()

    await select.callback(interaction)

    assert view.verify_channel_id == 555


# --- EditWelcomeMessageButton + WelcomeMessageModal ---


async def test_edit_welcome_message_button_opens_modal():
    view = SetupView({})
    button = next(c for c in view.children if isinstance(c, EditWelcomeMessageButton))
    interaction = FakeInteraction()

    await button.callback(interaction)

    assert len(interaction.response.sent) == 1
    assert isinstance(interaction.response.sent[0], WelcomeMessageModal)


async def test_welcome_message_modal_updates_wizard_state():
    view = SetupView({})
    modal = WelcomeMessageModal(view)
    modal.message._value = "A brand new welcome message!"
    interaction = FakeInteraction()

    await modal.on_submit(interaction)

    assert view.welcome_message == "A brand new welcome message!"


# --- FinishSetupButton ---


async def test_finish_setup_requires_role_and_channel():
    view = SetupView({})  # neither role nor channel set
    button = next(c for c in view.children if isinstance(c, FinishSetupButton))
    interaction = FakeInteraction()

    await button.callback(interaction)

    assert "choose both" in interaction.response.sent[0].lower()


async def test_finish_setup_saves_and_disables_view(
    settings_manager_instance, monkeypatch
):
    import ui.setup_wizard as wizard_module

    monkeypatch.setattr(wizard_module, "settings_manager", settings_manager_instance)

    view = SetupView(
        {"verified_role_id": 100, "verify_channel_id": 200, "method": "captcha"}
    )
    button = next(c for c in view.children if isinstance(c, FinishSetupButton))
    interaction = FakeInteraction()
    interaction.guild_id = 777

    await button.callback(interaction)

    saved = await settings_manager_instance.get(777)
    assert saved["method"] == "captcha"
    assert saved["verified_role_id"] == 100
    assert saved["verify_channel_id"] == 200
    assert all(child.disabled for child in view.children)


# --- CancelSetupButton ---


async def test_cancel_disables_view_without_saving(
    settings_manager_instance, monkeypatch
):
    import ui.setup_wizard as wizard_module

    monkeypatch.setattr(wizard_module, "settings_manager", settings_manager_instance)

    view = SetupView({"verified_role_id": 100, "verify_channel_id": 200})
    button = next(c for c in view.children if isinstance(c, CancelSetupButton))
    interaction = FakeInteraction()
    interaction.guild_id = 888

    await button.callback(interaction)

    saved = await settings_manager_instance.get(888)
    assert saved["verified_role_id"] is None  # nothing was saved
    assert all(child.disabled for child in view.children)
    assert "cancelled" in interaction.response.sent[0].lower()
