"""
SettingsManager

Handles all reads/writes of per-guild verification settings.

Design goals:
- A guild with no row in the DB behaves exactly like DEFAULT_SETTINGS (zero setup required).
- Settings are cached in memory per guild so hot paths (on_member_join, button clicks)
  never wait on a DB round-trip.
- Partial updates (e.g. "just change the method") merge into existing settings
  instead of overwriting the whole thing.
- Deep-merge with defaults means new setting keys you add later automatically
  show up for existing guilds without a migration.

Note: the underlying SQLite table/column names (guild_config / config_json)
are kept as-is even after this rename, since changing them would require a
data migration for anyone who already has a populated bot.db.
"""

import json
import copy
import logging
import aiosqlite
from pathlib import Path

from .defaults import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent / "database" / "bot.db"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into a copy of base. override wins on conflicts."""
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class SettingsManager:
    def __init__(self):
        self._cache: dict[int, dict] = {}  # guild_id -> settings dict
        self._db: aiosqlite.Connection | None = None

    async def init(self):
        """Call once on bot startup before any other method is used."""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(DB_PATH)
        await self._db.execute(
            """
            CREATE TABLE IF NOT EXISTS guild_config (
                guild_id INTEGER PRIMARY KEY,
                config_json TEXT NOT NULL
            )
            """
        )
        await self._db.commit()
        logger.info("Settings database ready at %s", DB_PATH)

    async def close(self):
        if self._db:
            await self._db.close()
            logger.debug("Settings database connection closed")

    async def get(self, guild_id: int) -> dict:
        """
        Return this guild's settings, merged over defaults.
        Never raises - always returns a usable dict, even for a brand-new guild.
        """
        if guild_id in self._cache:
            logger.debug("Settings cache hit for guild %s", guild_id)
            return self._cache[guild_id]

        async with self._db.execute(
            "SELECT config_json FROM guild_config WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            logger.debug("No stored settings for guild %s - using defaults", guild_id)
            settings = copy.deepcopy(DEFAULT_SETTINGS)
        else:
            stored = json.loads(row[0])
            # deep-merge so any new default keys added after this guild first
            # saved settings still show up, without needing a migration
            settings = _deep_merge(DEFAULT_SETTINGS, stored)
            logger.debug("Loaded stored settings for guild %s from database", guild_id)

        self._cache[guild_id] = settings
        return settings

    async def update(self, guild_id: int, updates: dict) -> dict:
        """
        Merge `updates` into this guild's existing settings and persist it.
        Example: await settings_manager.update(guild_id, {"method": "captcha"})
        """
        current = await self.get(guild_id)
        new_settings = _deep_merge(current, updates)

        await self._db.execute(
            """
            INSERT INTO guild_config (guild_id, config_json)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET config_json = excluded.config_json
            """,
            (guild_id, json.dumps(new_settings)),
        )
        await self._db.commit()

        self._cache[guild_id] = new_settings
        logger.info("Settings updated for guild %s: %s", guild_id, list(updates.keys()))
        return new_settings

    async def reset(self, guild_id: int) -> dict:
        """Delete a guild's stored settings, reverting it to defaults."""
        await self._db.execute(
            "DELETE FROM guild_config WHERE guild_id = ?", (guild_id,)
        )
        await self._db.commit()
        self._cache.pop(guild_id, None)
        logger.info("Settings reset to defaults for guild %s", guild_id)
        return copy.deepcopy(DEFAULT_SETTINGS)


# Single shared instance the rest of the bot imports and uses.
settings_manager = SettingsManager()
