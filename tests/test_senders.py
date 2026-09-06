import pytest
from core import email_sender, sms_sender


async def test_email_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    assert email_sender.is_configured() is False

    with pytest.raises(email_sender.EmailNotConfigured):
        await email_sender.send_verification_email(
            "test@example.com", "ABC123", "Test Guild"
        )


async def test_email_configured_when_all_vars_set(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USERNAME", "user@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "password")
    assert email_sender.is_configured() is True


async def test_sms_not_configured_by_default(monkeypatch):
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_FROM_NUMBER", raising=False)
    assert sms_sender.is_configured() is False

    with pytest.raises(sms_sender.SMSNotConfigured):
        await sms_sender.send_verification_sms("+14155551234", "ABC123", "Test Guild")


async def test_sms_configured_when_all_vars_set(monkeypatch):
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setenv("TWILIO_FROM_NUMBER", "+15005550006")
    assert sms_sender.is_configured() is True
