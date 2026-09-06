"""
Shared email sending, used by modules/email_verification.py.

Credentials are bot-wide, loaded from environment variables - NOT stored in
per-guild settings, because:
  1. One bot sends from one address regardless of which server triggered it.
  2. Per-guild settings are readable in full via /verify-view; SMTP
     credentials must never end up in that JSON dump.

Credentials are read fresh from os.environ on every call, not cached into
module-level constants at import time. Reading them at import time would
freeze whatever value existed in os.environ at the moment this module was
FIRST imported - if that happens before .env has been loaded (e.g. because
some other module imports this one, directly or transitively, before the
entry point calls load_dotenv()), the credentials would be permanently
None regardless of what's actually in .env. Reading them lazily means
import order can never cause this class of bug again.
"""

import os
from email.message import EmailMessage

import aiosmtplib


class EmailNotConfigured(Exception):
    """Raised when SMTP credentials are missing from .env."""


def is_configured() -> bool:
    return all(
        [os.getenv("SMTP_HOST"), os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")]
    )


async def send_verification_email(to_address: str, code: str, guild_name: str) -> None:
    if not is_configured():
        raise EmailNotConfigured(
            "SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD are not set in .env"
        )

    smtp_host = os.getenv("SMTP_HOST")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_from_address = os.getenv("SMTP_FROM_ADDRESS", smtp_username)

    message = EmailMessage()
    message["From"] = smtp_from_address
    message["To"] = to_address
    message["Subject"] = f"Your verification code for {guild_name}"
    message.set_content(
        f"Your verification code is: {code}\n\n"
        "This code expires in 5 minutes. If you didn't request this, you can ignore this email."
    )

    await aiosmtplib.send(
        message,
        hostname=smtp_host,
        port=smtp_port,
        username=smtp_username,
        password=smtp_password,
        start_tls=True,
    )
