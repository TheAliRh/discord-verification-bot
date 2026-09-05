from core.prechecks import passes_prechecks
from tests.conftest import FakeMember, FakeInteraction


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
