import io
from PIL import Image

from modules.image_captcha import (
    render_captcha_image,
    ImageCaptchaButton,
    ImageCaptchaModal,
    EnterCodeButton,
    ImageCaptchaVerificationView,
    _IMAGE_SIZE,
)
from tests.conftest import FakeRole, FakeMember, FakeGuild, FakeInteraction


DEFAULT_SETTINGS = {
    "verified_role_id": 100,
    "min_account_age_days": 0,
    "method_settings": {"captcha": {"length": 6, "type": "alphanumeric"}},
}


def test_render_captcha_image_produces_valid_png():
    buffer = render_captcha_image("ABC234")
    assert isinstance(buffer, io.BytesIO)

    image = Image.open(buffer)
    assert image.format == "PNG"
    assert image.size == _IMAGE_SIZE


def test_render_captcha_image_varies_between_calls():
    """Two renders of the same code shouldn't be pixel-identical (random noise/rotation)."""
    buffer1 = render_captcha_image("ABC234")
    buffer2 = render_captcha_image("ABC234")
    assert buffer1.getvalue() != buffer2.getvalue()


async def test_click_sends_image_attachment_and_enter_code_view(monkeypatch):
    import settings as settings_pkg

    interaction = FakeInteraction()

    async def fake_get(guild_id):
        return DEFAULT_SETTINGS

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = ImageCaptchaButton()
    await button.callback(interaction)

    assert len(interaction.response.sent) == 1
    assert "code shown" in interaction.response.sent[0].lower()


async def test_click_blocked_by_precheck(monkeypatch):
    import settings as settings_pkg

    member = FakeMember(user_id=1, created_days_ago=1)
    interaction = FakeInteraction(user=member)
    settings_with_age_check = {**DEFAULT_SETTINGS, "min_account_age_days": 7}

    async def fake_get(guild_id):
        return settings_with_age_check

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = ImageCaptchaButton()
    await button.callback(interaction)

    assert "day" in interaction.response.sent[0].lower()


async def test_enter_code_button_opens_modal():
    interaction = FakeInteraction()
    button = EnterCodeButton(settings={"verified_role_id": 100})
    await button.callback(interaction)

    assert len(interaction.response.sent) == 1
    assert isinstance(interaction.response.sent[0], ImageCaptchaModal)


async def test_correct_code_grants_verification():
    from core.challenge_store import store_challenge

    verified_role = FakeRole(100)
    guild = FakeGuild(roles=[verified_role])
    interaction = FakeInteraction(guild=guild)
    store_challenge(interaction.guild_id, interaction.user.id, "XYZ987")

    modal = ImageCaptchaModal(settings={"verified_role_id": 100})
    modal.answer._value = "XYZ987"
    await modal.on_submit(interaction)

    assert 100 in interaction.user.added_roles


def test_view_has_static_custom_id_and_is_persistent():
    view = ImageCaptchaVerificationView()
    assert view.timeout is None
    assert view.children[0].custom_id == "verify:image_captcha:click"
