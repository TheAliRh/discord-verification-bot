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


# --- max_attempts enforcement (the actual feature being tested) ---


async def test_deny_verified_shows_remaining_attempts():
    guild = FakeGuild(guild_id=1)
    interaction = FakeInteraction(guild=guild)
    settings = {"max_attempts": 3, "cooldown_seconds": 30}

    await service.deny_verified(interaction, settings, "Wrong code.")

    assert "2 attempt(s) remaining" in interaction.response.sent[0]
    assert "Click Verify to try again" in interaction.response.sent[0]


async def test_deny_verified_locks_out_after_max_attempts_reached():
    from core.attempt_tracker import is_locked_out

    guild = FakeGuild(guild_id=1)
    settings = {"max_attempts": 3, "cooldown_seconds": 30}

    # Fail 3 times (a fresh interaction each time, like separate clicks)
    for _ in range(3):
        interaction = FakeInteraction(guild=guild)
        await service.deny_verified(interaction, settings, "Wrong code.")

    assert "maximum of 3 failed attempts" in interaction.response.sent[0]
    assert "Try again in 30 second(s)" in interaction.response.sent[0]

    locked, remaining = is_locked_out(1, interaction.user.id)
    assert locked is True
    assert 0 < remaining <= 30


async def test_locked_out_user_is_blocked_by_prechecks_before_a_new_attempt():
    from core.prechecks import passes_prechecks
    from core.attempt_tracker import lock_out

    member = FakeMember(user_id=1)
    guild = FakeGuild(guild_id=1)
    interaction = FakeInteraction(user=member, guild=guild)
    lock_out(guild_id=1, user_id=1, cooldown_seconds=60)

    result = await passes_prechecks(interaction, {"min_account_age_days": 0})

    assert result is False
    assert "Too many failed attempts" in interaction.response.sent[0]
    assert (
        "Click Verify to try again" not in interaction.response.sent[0]
    )  # suggest_retry=False


async def test_lockout_notice_does_not_double_count_as_an_attempt():
    """Being told 'you're locked out' must not itself consume another attempt."""
    from core.prechecks import passes_prechecks
    from core.attempt_tracker import lock_out, get_failed_attempts

    member = FakeMember(user_id=1)
    guild = FakeGuild(guild_id=1)
    interaction = FakeInteraction(user=member, guild=guild)
    lock_out(guild_id=1, user_id=1, cooldown_seconds=60)

    await passes_prechecks(interaction, {"min_account_age_days": 0})
    await passes_prechecks(interaction, {"min_account_age_days": 0})

    assert get_failed_attempts(1, 1) == 0  # lockout notices never increment the count


async def test_account_age_rejection_does_not_count_toward_max_attempts():
    from core.prechecks import passes_prechecks
    from core.attempt_tracker import get_failed_attempts

    member = FakeMember(user_id=1, created_days_ago=1)
    guild = FakeGuild(guild_id=1)
    interaction = FakeInteraction(user=member, guild=guild)
    settings = {"min_account_age_days": 7, "max_attempts": 3}

    await passes_prechecks(interaction, settings)

    assert (
        get_failed_attempts(1, 1) == 0
    )  # account-age rejection is not a "wrong guess"


async def test_kick_on_fail_kicks_member_after_max_attempts():
    member = FakeMember(user_id=1)
    guild = FakeGuild(guild_id=1)
    settings = {"max_attempts": 2, "cooldown_seconds": 30, "kick_on_fail": True}

    for _ in range(2):
        interaction = FakeInteraction(user=member, guild=guild)
        await service.deny_verified(interaction, settings, "Wrong code.")

    assert member.kicked is True
    assert "removed from the server" in interaction.response.sent[0]


async def test_kick_on_fail_disabled_does_not_kick():
    member = FakeMember(user_id=1)
    guild = FakeGuild(guild_id=1)
    settings = {"max_attempts": 2, "cooldown_seconds": 30, "kick_on_fail": False}

    for _ in range(2):
        interaction = FakeInteraction(user=member, guild=guild)
        await service.deny_verified(interaction, settings, "Wrong code.")

    assert member.kicked is False
    assert "Try again in 30 second(s)" in interaction.response.sent[0]


async def test_kick_forbidden_falls_back_gracefully():
    member = FakeMember(user_id=1)
    member.kick_forbidden = True
    guild = FakeGuild(guild_id=1)
    settings = {"max_attempts": 1, "cooldown_seconds": 30, "kick_on_fail": True}

    interaction = FakeInteraction(user=member, guild=guild)
    await service.deny_verified(interaction, settings, "Wrong code.")  # must not raise

    assert member.kicked is False
    assert "Try again in 30 second(s)" in interaction.response.sent[0]


async def test_successful_verification_resets_attempt_count():
    from core.attempt_tracker import record_failed_attempt, get_failed_attempts

    verified_role = FakeRole(100)
    guild = FakeGuild(roles=[verified_role])
    member = FakeMember(user_id=1)
    interaction = FakeInteraction(user=member, guild=guild)

    record_failed_attempt(guild.id, member.id)
    record_failed_attempt(guild.id, member.id)
    assert get_failed_attempts(guild.id, member.id) == 2

    await service.grant_verified(interaction, {"verified_role_id": 100})

    assert get_failed_attempts(guild.id, member.id) == 0


async def test_max_attempts_disabled_never_locks_out():
    guild = FakeGuild(guild_id=1)
    settings = {"max_attempts": 0}  # disabled

    for _ in range(10):
        interaction = FakeInteraction(guild=guild)
        await service.deny_verified(interaction, settings, "Wrong code.")

    from core.attempt_tracker import is_locked_out

    locked, _ = is_locked_out(1, interaction.user.id)
    assert locked is False
    assert "Click Verify to try again" in interaction.response.sent[0]
