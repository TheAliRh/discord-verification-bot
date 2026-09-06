"""
Shared SMS sending, used by modules/phone_verification.py.

Uses Twilio's REST API directly via aiohttp rather than Twilio's official
SDK, since that SDK is synchronous and would block the bot's event loop on
every send. Credentials are bot-wide, loaded from .env - same reasoning as
core/email_sender.py: they must never end up in per-guild settings, which
/verify-view dumps in full.

Requires a Twilio account (paid, per-message cost) with a verified sender
number capable of sending SMS in the destination country.
"""

import os
import aiohttp

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

_TWILIO_API_URL = "https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"


class SMSNotConfigured(Exception):
    """Raised when Twilio credentials are missing from .env."""


class SMSSendError(Exception):
    """Raised when Twilio's API rejects the request (bad number, insufficient funds, etc.)."""


def is_configured() -> bool:
    return all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER])


async def send_verification_sms(to_number: str, code: str, guild_name: str) -> None:
    if not is_configured():
        raise SMSNotConfigured(
            "TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_FROM_NUMBER are not set in .env"
        )
    # is_configured() already confirmed these are non-None, but mypy can't
    # infer that from a separate function call - narrow explicitly.
    assert (
        TWILIO_ACCOUNT_SID is not None
        and TWILIO_AUTH_TOKEN is not None
        and TWILIO_FROM_NUMBER is not None
    )

    url = _TWILIO_API_URL.format(sid=TWILIO_ACCOUNT_SID)
    body = {
        "To": to_number,
        "From": TWILIO_FROM_NUMBER,
        "Body": f"Your verification code for {guild_name} is: {code}",
    }
    auth = aiohttp.BasicAuth(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=body, auth=auth) as response:
            if response.status >= 300:
                error_text = await response.text()
                raise SMSSendError(f"Twilio returned {response.status}: {error_text}")
