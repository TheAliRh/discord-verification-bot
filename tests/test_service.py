import discord
from core import service
from tests.conftest import FakeRole, FakeMember, FakeGuild, FakeInteraction


async def test_grant_verified_success_swaps_roles():
    verified_role = FakeRole(100)
    unverified_role = FakeRole(200)
    guild = FakeGuild(roles=[verified_role, unverified_role])
    member = FakeMember(user_id=1, roles=[unverified_role])
    interaction = FakeInteraction(user=member, guild=guild)

    await service.grant_verified(
        interaction, {"verified_role_id": 100, "unverified_role_id": 200}
    )

    assert 100 in member.added_roles
    assert 200 in member.removed_roles
    assert interaction.response.sent[0].startswith("✅")


async def test_grant_verified_missing_role_id_configured():
    guild = FakeGuild()
    member = FakeMember(user_id=1)
    interaction = FakeInteraction(user=member, guild=guild)

    await service.grant_verified(interaction, {})

    assert "Verified role" in interaction.response.sent[0]
    assert len(member.added_roles) == 0


async def test_grant_verified_role_no_longer_exists():
    guild = FakeGuild(roles=[])  # role 999 doesn't exist
    member = FakeMember(user_id=1)
    interaction = FakeInteraction(user=member, guild=guild)

    await service.grant_verified(interaction, {"verified_role_id": 999})

    assert "no longer exists" in interaction.response.sent[0]
    assert len(member.added_roles) == 0


async def test_grant_verified_by_id_matches_interaction_path():
    """The OAuth2/HTTP path should produce identical role changes to the interaction path."""
    verified_role = FakeRole(100)
    unverified_role = FakeRole(200)
    member = FakeMember(user_id=1, roles=[unverified_role])
    guild = FakeGuild(
        guild_id=999, roles=[verified_role, unverified_role], member=member
    )

    class FakeBot:
        def get_guild(self, gid):
            return guild if gid == 999 else None

    ok, message = await service.grant_verified_by_id(
        FakeBot(),
        guild_id=999,
        user_id=1,
        settings={"verified_role_id": 100, "unverified_role_id": 200},
    )

    assert ok is True
    assert 100 in member.added_roles
    assert 200 in member.removed_roles


async def test_grant_verified_by_id_guild_not_found():
    class FakeBot:
        def get_guild(self, gid):
            return None

    ok, message = await service.grant_verified_by_id(
        FakeBot(), guild_id=999, user_id=1, settings={}
    )
    assert ok is False
    assert "Could not find that server" in message


async def test_grant_verified_by_id_member_not_found():
    guild = FakeGuild(guild_id=999, member=None)

    class FakeBot:
        def get_guild(self, gid):
            return guild

    ok, message = await service.grant_verified_by_id(
        FakeBot(), guild_id=999, user_id=1, settings={"verified_role_id": 100}
    )
    assert ok is False
    assert "Could not find you" in message


async def test_deny_verified_sends_message_and_logs():
    interaction = FakeInteraction()
    await service.deny_verified(interaction, {}, "Wrong code.")
    assert "Wrong code." in interaction.response.sent[0]
    assert interaction.response.sent[0].startswith("❌")
