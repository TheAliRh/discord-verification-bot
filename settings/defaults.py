"""
Default verification settings.

This is what a guild "sees" if it has never run /verify setup.
The bot should work out of the box with these values - no setup required.
"""

DEFAULT_SETTINGS = {
    "enabled": True,
    "method": "button",  # "button" | "captcha" | "math" | "email" | "phone" | "oauth2"
    "checks": [],  # extra stacked checks, e.g. ["min_account_age"]
    "unverified_role_id": None,  # None = no role gating before verification
    "verified_role_id": None,  # None = must be set by the server owner before verification does anything useful
    "verify_channel_id": None,  # None = bot will DM the user instead
    "min_account_age_days": 0,  # 0 = disabled
    "max_attempts": 3,
    "cooldown_seconds": 30,
    "kick_on_fail": False,
    "log_channel_id": None,
    "welcome_message": "Click the button below to verify and get access to the server.",
    # method-specific settings live in their own namespace so switching
    # methods doesn't clobber other methods' settings
    "method_settings": {
        "captcha": {"length": 6, "type": "alphanumeric"},  # "alphanumeric" | "numeric"
        "math": {"difficulty": "easy"},  # "easy" | "medium" | "hard"
        "email": {"length": 6, "cooldown_seconds": 60},
        "phone": {"length": 6, "cooldown_seconds": 60},
    },
}
