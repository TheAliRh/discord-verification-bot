"""
SettingsManager

Handles all reads/writes of per-guild verification settings.

Design goals:
- A guild with no row in the DB behaves exactly like DEFAULT_SETTINGS (zero setup required).
- Settings is cached in memory per guild so hot paths (on_member_join, button clicks)
  never wait on a DB round-trip.
- Partial updates (e.g. "just change the method") merge into existing settings
  instead of overwriting the whole thing.
- Deep-merge with defaults means new settings keys you add later automatically
  show up for existing guilds without a migration.
"""

import json
import copy
import aiosqlite
from pathlib import Path

from .defaults import DEFAULT_SETTINGS

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
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                settings_json TEXT NOT NULL
            )
            """
        )
        await self._db.commit()

    async def close(self):
        if self._db:
            await self._db.close()

    async def get(self, guild_id: int) -> dict:
        """
        Return this guild's settings, merged over defaults.
        Never raises - always returns a usable dict, even for a brand-new guild.
        """
        if guild_id in self._cache:
            return self._cache[guild_id]

        async with self._db.execute(
            "SELECT settings_json FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            settings = copy.deepcopy(DEFAULT_SETTINGS)
        else:
            stored = json.loads(row[0])
            # deep-merge so any new default keys added after this guild first
            # saved settings still show up, without needing a migration
            settings = _deep_merge(DEFAULT_SETTINGS, stored)

        self._cache[guild_id] = settings
        return settings

    async def update(self, guild_id: int, updates: dict) -> dict:
        """
        Merge `updates` into this guild's existing settings and persist it.
        Example: await settings.update(guild_id, {"method": "captcha"})
        """
        current = await self.get(guild_id)
        new_settings = _deep_merge(current, updates)

        await self._db.execute(
            """
            INSERT INTO guild_settings (guild_id, settings_json)
            VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET settings_json = excluded.settings_json
            """,
            (guild_id, json.dumps(new_settings)),
        )
        await self._db.commit()

        self._cache[guild_id] = new_settings
        return new_settings

    async def reset(self, guild_id: int) -> dict:
        """Delete a guild's stored settings, reverting it to defaults."""
        await self._db.execute(
            "DELETE FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        await self._db.commit()
        self._cache.pop(guild_id, None)
        return copy.deepcopy(DEFAULT_SETTINGS)


# Single shared instance the rest of the bot imports and uses.
settings_manager = SettingsManager()
