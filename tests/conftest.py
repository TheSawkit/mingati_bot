import os
from pathlib import Path

import pytest

from mingati.config import Settings
from mingati.database import Database

CONFIG_KEYS = {name.upper() for name in Settings.model_fields}


@pytest.fixture(autouse=True)
def isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in os.environ:
        if key.upper() in CONFIG_KEYS:
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
