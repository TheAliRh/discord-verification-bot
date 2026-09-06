import pytest
from core import discord_oauth


def test_is_configured_false_when_env_vars_unset(monkeypatch):
    monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
    monkeypatch.delenv("DISCORD_CLIENT_SECRET", raising=False)
    assert discord_oauth.is_configured() is False


def test_is_configured_true_when_both_set(monkeypatch):
    monkeypatch.setenv("DISCORD_CLIENT_ID", "some-id")
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "some-secret")
    assert discord_oauth.is_configured() is True


def test_build_authorize_url_raises_when_not_configured(monkeypatch):
    monkeypatch.delenv("DISCORD_CLIENT_ID", raising=False)
    with pytest.raises(discord_oauth.OAuthNotConfigured):
        discord_oauth.build_authorize_url("some-state")


def test_build_authorize_url_contains_expected_params(monkeypatch):
    monkeypatch.setenv("DISCORD_CLIENT_ID", "my-client-id")
    monkeypatch.setenv("DISCORD_CLIENT_SECRET", "my-secret")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback")

    url = discord_oauth.build_authorize_url("abc123")

    assert "client_id=my-client-id" in url
    assert "state=abc123" in url
    assert "response_type=code" in url
    assert "scope=identify" in url
