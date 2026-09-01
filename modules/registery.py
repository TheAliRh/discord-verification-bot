"""
Registry of available verification modules.

Central place to look up "which module handles config['method']".
Falls back to Button if a guild's configured method somehow doesn't
match any registered module (e.g. a method was removed in an update).
"""

from .button import ButtonVerification
from .captcha import CaptchaVerification
from .image_captcha import ImageCaptchaVerification
from .email_verification import EmailVerification
from .phone_verification import PhoneVerification
from .oauth2_verification import OAuth2Verification

MODULES = {
    "button": ButtonVerification(),
    "captcha": CaptchaVerification(),
    "image_captcha": ImageCaptchaVerification(),
    "email": EmailVerification(),
    "phone": PhoneVerification(),
    "oauth2": OAuth2Verification(),
}

DEFAULT_METHOD_KEY = "button"


def get_module(method_key: str):
    return MODULES.get(method_key, MODULES[DEFAULT_METHOD_KEY])


def all_persistent_views():
    """Used on bot startup to re-register every module's persistent view."""
    return [module.get_persistent_view() for module in MODULES.values()]
