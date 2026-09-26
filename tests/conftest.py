import os
from pathlib import Path

import pytest

from mingati.database import Database

CONFIG_PREFIXES = (
    "DISCORD_",
    "CHANNEL_",
    "ROLE_",
    "LLM_",
    "GEMINI_",
    "DATABASE_",
    "LOG_",
    "TIMEZONE",
)


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in os.environ:
        if key.startswith(CONFIG_PREFIXES):
            monkeypatch.delenv(key)


@pytest.fixture
async def open_database(tmp_path: Path):
    opened: list[Database] = []

    async def open_(migrations: Path | None = None, name: str = "test.db") -> Database:
        database = Database(tmp_path / name, migrations)
        opened.append(database)
        await database.connect()
        return database

    yield open_
    for database in opened:
        await database.close()


@pytest.fixture
async def database(open_database) -> Database:
    return await open_database()
