import asyncio
import logging
import re
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from importlib import resources
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger(__name__)

MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

Params = Sequence[Any] | dict[str, Any]


class DatabaseError(RuntimeError):
    pass


def discover_migrations(directory: Traversable) -> list[tuple[int, str]]:
    """Return (version, sql) pairs sorted by version; versions must be contiguous from 1."""
    if not directory.is_dir():
        return []
    migrations: list[tuple[int, str]] = []
    for entry in directory.iterdir():
        match = MIGRATION_NAME.match(entry.name)
        if match:
            migrations.append((int(match.group(1)), entry.read_text(encoding="utf-8")))
    migrations.sort()

    expected = list(range(1, len(migrations) + 1))
    if [version for version, _ in migrations] != expected:
        raise DatabaseError(f"Migrations must be numbered contiguously from 0001: {migrations!r}")
    return migrations


class Database:
    """Single shared SQLite connection; accesses are serialized so transactions never interleave."""

    def __init__(self, path: Path, migrations: Traversable | None = None) -> None:
        self.path = path
        self._migrations = migrations or resources.files("mingati") / "migrations"
        self._connection: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open the database, enable integrity pragmas and apply pending migrations."""
        if self.path != Path(":memory:"):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path, isolation_level=None)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.execute("PRAGMA journal_mode = WAL")
        await self._connection.execute("PRAGMA synchronous = NORMAL")
        await self._connection.execute("PRAGMA busy_timeout = 5000")
        await self._migrate()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise DatabaseError("Database is not connected")
        return self._connection

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiosqlite.Connection]:
        """Run several statements atomically; rolls back if the block raises."""
        async with self._lock:
            await self.connection.execute("BEGIN IMMEDIATE")
            try:
                yield self.connection
            except BaseException:
                await self.connection.execute("ROLLBACK")
                raise
            await self.connection.execute("COMMIT")

    async def execute(self, sql: str, params: Params = ()) -> int:
        """Run one write statement in its own transaction and return the affected row count."""
        async with self.transaction() as connection:
            cursor = await connection.execute(sql, params)
            return cursor.rowcount

    async def fetch_one(self, sql: str, params: Params = ()) -> aiosqlite.Row | None:
        async with self._lock:
            cursor = await self.connection.execute(sql, params)
            return await cursor.fetchone()

    async def fetch_all(self, sql: str, params: Params = ()) -> list[aiosqlite.Row]:
        async with self._lock:
            cursor = await self.connection.execute(sql, params)
            return list(await cursor.fetchall())

    async def schema_version(self) -> int:
        row = await self.fetch_one("PRAGMA user_version")
        return int(row[0]) if row else 0

    async def _migrate(self) -> None:
        current = await self.schema_version()
        for version, sql in discover_migrations(self._migrations):
            if version <= current:
                continue
            log.info("Applying database migration %04d", version)
            async with self._lock:
                try:
                    await self.connection.executescript(
                        f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {version};\nCOMMIT;"
                    )
                except Exception:
                    if self.connection.in_transaction:
                        await self.connection.execute("ROLLBACK")
                    raise
