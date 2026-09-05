"""
Shared fixtures for the whole test suite.

Fake Discord objects here are deliberately minimal - just enough attributes
and methods for the code under test to run against, not full discord.py
mocks. This mirrors real discord.py's interfaces closely enough (add_roles,
get_role, response.send_message, etc.) without needing network access or
a real bot token, which this sandbox/CI environment doesn't have anyway.
"""

import sys
from pathlib import Path

import pytest
import discord

# Make the project root importable regardless of where pytest is invoked from.
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fake Discord objects
# ---------------------------------------------------------------------------


class FakeRole:
    def __init__(self, role_id):
        self.id = role_id

    def __eq__(self, other):
        return isinstance(other, FakeRole) and self.id == other.id

    def __hash__(self):
        return hash(self.id)

    def __ge__(self, other):
        return self.id >= other.id

    def __lt__(self, other):
        return self.id < other.id


class FakeMember:
    def __init__(self, user_id, name="TestUser", roles=None, created_days_ago=365):
        import datetime

        self.id = user_id
        self.name = name
        self.roles = roles or []
        self.created_at = discord.utils.utcnow() - datetime.timedelta(
            days=created_days_ago
        )
        self.added_roles = []
        self.removed_roles = []
        self.dms_sent = []
        self.dm_forbidden = False

    async def add_roles(self, role, reason=None):
        self.added_roles.append(role.id)
        self.roles.append(role)

    async def remove_roles(self, role, reason=None):
        self.removed_roles.append(role.id)
        self.roles = [r for r in self.roles if r.id != role.id]

    async def send(self, content=None, **kwargs):
        if self.dm_forbidden:
            raise discord.Forbidden(response=FakeHTTPResponse(), message="DMs closed")
        self.dms_sent.append(content)

    def __str__(self):
        return f"{self.name}#0001"


class FakeHTTPResponse:
    """Minimal stand-in for the aiohttp response discord.HTTPException wraps."""

    status = 403
    reason = "Forbidden"
    headers = {}
    request_info = None


class FakeGuild:
    def __init__(self, guild_id=1000, name="Test Guild", roles=None, member=None):
        self.id = guild_id
        self.name = name
        self._roles = {r.id: r for r in (roles or [])}
        self._member = member

    def get_role(self, role_id):
        return self._roles.get(role_id)

    def get_member(self, user_id):
        if self._member and self._member.id == user_id:
            return self._member
        return None

    def get_channel(self, channel_id):
        return None  # no log channel by default - tests opt in by overriding this

    async def fetch_member(self, user_id):
        member = self.get_member(user_id)
        if member is None:
            raise discord.NotFound(
                response=FakeHTTPResponse(), message="Member not found"
            )
        return member


class FakeResponse:
    def __init__(self):
        self.sent = []
        self.sent_kwargs = []
        self._done = False

    async def send_message(self, content=None, **kwargs):
        self.sent.append(content)
        self.sent_kwargs.append(kwargs)
        self._done = True

    async def send_modal(self, modal):
        self.sent.append(modal)
        self.sent_kwargs.append({})
        self._done = True

    async def edit_message(self, content=None, **kwargs):
        self.sent.append(content)
        self.sent_kwargs.append(kwargs)
        self._done = True

    def is_done(self):
        return self._done


class FakeFollowup:
    def __init__(self):
        self.sent = []

    async def send(self, content=None, **kwargs):
        self.sent.append(content)


class FakeInteraction:
    def __init__(self, user=None, guild=None):
        self.user = user or FakeMember(1)
        self.guild = guild or FakeGuild()
        self.guild_id = self.guild.id if self.guild else None
        self.response = FakeResponse()
        self.followup = FakeFollowup()
        self.command = None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_member():
    return FakeMember(user_id=1)


@pytest.fixture
def fake_guild():
    return FakeGuild()


@pytest.fixture
def fake_interaction():
    return FakeInteraction()


@pytest.fixture(autouse=True)
def reset_in_memory_stores():
    """
    Several modules keep module-level in-memory state (challenge codes,
    rate-limit timestamps, OAuth2 state tokens). Without resetting these
    between tests, one test's data can leak into another and cause
    order-dependent failures.
    """
    from core import challenge_store, rate_limiter, oauth_state

    challenge_store._CHALLENGES.clear()
    rate_limiter._LAST_ACTION.clear()
    oauth_state._STATES.clear()

    yield

    challenge_store._CHALLENGES.clear()
    rate_limiter._LAST_ACTION.clear()
    oauth_state._STATES.clear()


@pytest.fixture
async def settings_manager_instance(tmp_path):
    """A real SettingsManager backed by a throwaway SQLite file per test."""
    import settings.manager as manager_module
    from settings.manager import SettingsManager

    original_path = manager_module.DB_PATH
    manager_module.DB_PATH = tmp_path / "test_bot.db"

    sm = SettingsManager()
    await sm.init()

    yield sm

    await sm.close()
    manager_module.DB_PATH = original_path
