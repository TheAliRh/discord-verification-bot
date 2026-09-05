from modules.registry import get_module, all_persistent_views, MODULES
from modules.button import ButtonVerificationView


def test_all_six_methods_registered():
    assert set(MODULES.keys()) == {
        "button",
        "captcha",
        "image_captcha",
        "email",
        "phone",
        "oauth2",
    }


def test_get_module_returns_correct_instance_for_known_keys():
    for key, module in MODULES.items():
        assert get_module(key) is module


def test_get_module_falls_back_to_button_for_unknown_key():
    assert get_module("totally_unknown_method") is MODULES["button"]


def test_all_persistent_views_returns_one_per_module():
    views = all_persistent_views()
    assert len(views) == len(MODULES)


def test_persistent_views_have_static_custom_ids():
    """Required for bot.add_view() to correctly re-attach buttons after a restart."""
    views = all_persistent_views()
    for view in views:
        for item in view.children:
            assert item.custom_id is not None
            assert not item.custom_id.startswith(
                "discord.py"
            )  # not an auto-generated random id


def test_button_view_is_persistent():
    view = ButtonVerificationView()
    assert view.timeout is None
