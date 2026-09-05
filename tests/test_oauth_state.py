from core.oauth_state import create_state, consume_state


def test_create_and_consume_round_trip():
    token = create_state(guild_id=111, user_id=222)
    entry = consume_state(token)
    assert entry["guild_id"] == 111
    assert entry["user_id"] == 222


def test_state_token_is_single_use():
    token = create_state(guild_id=111, user_id=222)
    consume_state(token)
    assert consume_state(token) is None  # replay rejected


def test_unknown_token_returns_none():
    assert consume_state("not-a-real-token") is None


def test_different_tokens_are_independent():
    token1 = create_state(guild_id=1, user_id=1)
    token2 = create_state(guild_id=2, user_id=2)

    entry2 = consume_state(token2)
    assert entry2["guild_id"] == 2

    entry1 = consume_state(token1)  # still valid, unaffected by token2's consumption
    assert entry1["guild_id"] == 1
