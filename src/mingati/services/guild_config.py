from mingati.database import Database


class GuildConfigStore:
    """Small per-guild key/value state that must survive restarts (e.g. where the hub lives)."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(self, guild_id: int, key: str) -> str | None:
        row = await self.database.fetch_one(
            "SELECT value FROM guild_config WHERE guild_id = ? AND key = ?", (guild_id, key)
        )
        return row["value"] if row else None

    async def set(self, guild_id: int, key: str, value: str) -> None:
        await self.database.execute(
            "INSERT INTO guild_config (guild_id, key, value) VALUES (?, ?, ?)"
            " ON CONFLICT (guild_id, key) DO UPDATE SET value = excluded.value",
            (guild_id, key, value),
        )
