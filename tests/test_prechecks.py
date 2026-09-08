from core.prechecks import passes_prechecks
from tests.conftest import FakeMember, FakeInteraction, FakeGuild


async def test_disabled_check_always_passes():
    brand_new_user = FakeMember(user_id=1, created_days_ago=0)
    interaction = FakeInteraction(user=brand_new_user)
    result = await passes_prechecks(interaction, {"min_account_age_days": 0})
    assert result is True
    assert len(interaction.response.sent) == 0


async def test_old_enough_account_passes():
    old_user = FakeMember(user_id=1, created_days_ago=30)
    interaction = FakeInteraction(user=old_user)
    result = await passes_prechecks(interaction, {"min_account_age_days": 7})
    assert result is True
    assert len(interaction.response.sent) == 0


async def test_too_new_account_fails_with_message():
    new_user = FakeMember(user_id=1, created_days_ago=2)
    interaction = FakeInteraction(user=new_user)
    result = await passes_prechecks(interaction, {"min_account_age_days": 7})
    assert result is False
    assert len(interaction.response.sent) == 1
    assert "7 day" in interaction.response.sent[0]
    assert "2 day" in interaction.response.sent[0]


async def test_exact_boundary_passes():
    """Account exactly at the minimum age should pass (>=, not >)."""
    boundary_user = FakeMember(user_id=1, created_days_ago=7)
    interaction = FakeInteraction(user=boundary_user)
    result = await passes_prechecks(interaction, {"min_account_age_days": 7})
    assert result is True


# --- enabled: the actual bug being fixed - previously checked only in on_member_join ---


async def test_disabled_verification_blocks_the_button_itself():
    interaction = FakeInteraction()
    result = await passes_prechecks(interaction, {"enabled": False})
    assert result is False
    assert "turned off" in interaction.response.sent[0].lower()


async def test_enabled_defaults_to_true_when_key_missing():
    """If 'enabled' isn't in the dict at all (shouldn't happen via real settings, but defensively),
    verification must default to ON, not silently deny everyone."""
    interaction = FakeInteraction()
    result = await passes_prechecks(interaction, {})
    assert result is True


async def test_disabled_check_runs_before_lockout_and_account_age():
    """enabled=False should short-circuit immediately, not fall through to other checks."""
    from core.attempt_tracker import lock_out

    member = FakeMember(user_id=1, created_days_ago=1)  # would also fail account age
    guild = FakeGuild(guild_id=1)
    interaction = FakeInteraction(user=member, guild=guild)
    lock_out(guild_id=1, user_id=1, cooldown_seconds=60)  # would also be locked out

    result = await passes_prechecks(
        interaction, {"enabled": False, "min_account_age_days": 100}
    )

    assert result is False
    assert "turned off" in interaction.response.sent[0].lower()
    assert "locked out" not in interaction.response.sent[0].lower()
    assert "account" not in interaction.response.sent[0].lower()


async def test_disabled_rejection_does_not_count_as_an_attempt():
    from core.attempt_tracker import get_failed_attempts

    interaction = FakeInteraction(guild=FakeGuild(guild_id=1))
    await passes_prechecks(interaction, {"enabled": False})

    assert get_failed_attempts(1, interaction.user.id) == 0
