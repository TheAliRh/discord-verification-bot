"""
Shared email sending, used by modules/email_verification.py.

Credentials are bot-wide, loaded from environment variables - NOT stored in
per-guild settings, because:
  1. One bot sends from one address regardless of which server triggered it.
  2. Per-guild settings are readable in full via /verify-view; SMTP
     credentials must never end up in that JSON dump.
"""

import os
from email.message import EmailMessage

import aiosmtplib

SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM_ADDRESS = os.getenv("SMTP_FROM_ADDRESS", SMTP_USERNAME)


class EmailNotConfigured(Exception):
    """Raised when SMTP credentials are missing from .env."""


def is_configured() -> bool:
    return all([SMTP_HOST, SMTP_USERNAME, SMTP_PASSWORD])


async def send_verification_email(to_address: str, code: str, guild_name: str):
    if not is_configured():
        raise EmailNotConfigured(
            "SMTP_HOST / SMTP_USERNAME / SMTP_PASSWORD are not set in .env"
        )

    message = EmailMessage()
    message["From"] = SMTP_FROM_ADDRESS
    message["To"] = to_address
    message["Subject"] = f"Your verification code for {guild_name}"
    message.set_content(
        f"Your verification code is: {code}\n\n"
        "This code expires in 5 minutes. If you didn't request this, you can ignore this email."
    )

    await aiosmtplib.send(
        message,
        hostname=SMTP_HOST,
        port=SMTP_PORT,
        username=SMTP_USERNAME,
        password=SMTP_PASSWORD,
        start_tls=True,
    )
