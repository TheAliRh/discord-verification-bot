import pytest
from core import email_sender, sms_sender


async def test_email_not_configured_by_default(monkeypatch):
    monkeypatch.setattr(email_sender, "SMTP_HOST", None)
    monkeypatch.setattr(email_sender, "SMTP_USERNAME", None)
    monkeypatch.setattr(email_sender, "SMTP_PASSWORD", None)
    assert email_sender.is_configured() is False

    with pytest.raises(email_sender.EmailNotConfigured):
        await email_sender.send_verification_email(
            "test@example.com", "ABC123", "Test Guild"
        )


async def test_email_configured_when_all_vars_set(monkeypatch):
    monkeypatch.setattr(email_sender, "SMTP_HOST", "smtp.example.com")
    monkeypatch.setattr(email_sender, "SMTP_USERNAME", "user@example.com")
    monkeypatch.setattr(email_sender, "SMTP_PASSWORD", "password")
    assert email_sender.is_configured() is True


async def test_sms_not_configured_by_default(monkeypatch):
    monkeypatch.setattr(sms_sender, "TWILIO_ACCOUNT_SID", None)
    monkeypatch.setattr(sms_sender, "TWILIO_AUTH_TOKEN", None)
    monkeypatch.setattr(sms_sender, "TWILIO_FROM_NUMBER", None)
    assert sms_sender.is_configured() is False

    with pytest.raises(sms_sender.SMSNotConfigured):
        await sms_sender.send_verification_sms("+14155551234", "ABC123", "Test Guild")


async def test_sms_configured_when_all_vars_set(monkeypatch):
    monkeypatch.setattr(sms_sender, "TWILIO_ACCOUNT_SID", "sid")
    monkeypatch.setattr(sms_sender, "TWILIO_AUTH_TOKEN", "token")
    monkeypatch.setattr(sms_sender, "TWILIO_FROM_NUMBER", "+15005550006")
    assert sms_sender.is_configured() is True
