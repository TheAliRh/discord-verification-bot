from modules.oauth2_verification import (
    OAuth2VerifyButton,
    ContinueWithDiscordView,
    OAuth2VerificationView,
)
from core.oauth_state import consume_state
from tests.conftest import FakeMember, FakeInteraction


async def test_click_not_configured_gives_clear_message(monkeypatch):
    import settings as settings_pkg
    from core import discord_oauth

    monkeypatch.setattr(discord_oauth, "DISCORD_CLIENT_ID", None)
    monkeypatch.setattr(discord_oauth, "DISCORD_CLIENT_SECRET", None)

    async def fake_get(guild_id):
        return {"min_account_age_days": 0}

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    interaction = FakeInteraction()
    button = OAuth2VerifyButton()
    await button.callback(interaction)

    assert "isn't fully set up" in interaction.response.sent[0]


async def test_click_configured_creates_state_and_sends_link(monkeypatch):
    import settings as settings_pkg
    from core import discord_oauth

    monkeypatch.setattr(discord_oauth, "DISCORD_CLIENT_ID", "my-client-id")
    monkeypatch.setattr(discord_oauth, "DISCORD_CLIENT_SECRET", "my-secret")
    monkeypatch.setattr(
        discord_oauth, "OAUTH_REDIRECT_URI", "http://localhost:8080/oauth/callback"
    )

    async def fake_get(guild_id):
        return {"min_account_age_days": 0}

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    interaction = FakeInteraction(user=FakeMember(user_id=42))
    interaction.guild_id = 999
    button = OAuth2VerifyButton()
    await button.callback(interaction)

    assert len(interaction.response.sent_kwargs) == 1
    view = interaction.response.sent_kwargs[0]["view"]
    assert isinstance(view, ContinueWithDiscordView)

    link_button = view.children[0]
    assert link_button.url.startswith("https://discord.com/oauth2/authorize")
    assert "client_id=my-client-id" in link_button.url

    # The state embedded in the URL should be consumable and resolve to the right guild/user
    from urllib.parse import urlparse, parse_qs

    query = parse_qs(urlparse(link_button.url).query)
    state_token = query["state"][0]
    state = consume_state(state_token)
    assert state == {"guild_id": 999, "user_id": 42, "expires_at": state["expires_at"]}


async def test_click_blocked_by_precheck(monkeypatch):
    import settings as settings_pkg

    member = FakeMember(user_id=1, created_days_ago=1)
    interaction = FakeInteraction(user=member)

    async def fake_get(guild_id):
        return {"min_account_age_days": 7}

    monkeypatch.setattr(settings_pkg.settings_manager, "get", fake_get)

    button = OAuth2VerifyButton()
    await button.callback(interaction)

    assert "day" in interaction.response.sent[0].lower()


def test_continue_with_discord_view_has_link_button_with_url():
    view = ContinueWithDiscordView(
        authorize_url="https://discord.com/oauth2/authorize?foo=bar"
    )
    button = view.children[0]
    assert button.style.name == "link"
    assert button.url == "https://discord.com/oauth2/authorize?foo=bar"


def test_entry_view_has_static_custom_id_and_is_persistent():
    view = OAuth2VerificationView()
    assert view.timeout is None
    assert view.children[0].custom_id == "verify:oauth2:click"
