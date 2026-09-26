from pathlib import Path

import pytest

from mingati.database import Database, DatabaseError, discover_migrations


def write_migrations(directory: Path, *scripts: str) -> Path:
    directory.mkdir(exist_ok=True)
    for index, sql in enumerate(scripts, start=1):
        (directory / f"{index:04d}_step.sql").write_text(sql)
    return directory


async def test_applies_migrations_in_order_and_tracks_version(tmp_path: Path) -> None:
    migrations = write_migrations(
        tmp_path / "migrations",
        "CREATE TABLE a (id INTEGER PRIMARY KEY);",
        "ALTER TABLE a ADD COLUMN name TEXT;",
    )
    database = Database(tmp_path / "db" / "test.db", migrations)
    await database.connect()

    await database.execute("INSERT INTO a (name) VALUES (?)", ("billy",))

    assert await database.schema_version() == 2
    row = await database.fetch_one("SELECT name FROM a")
    assert row is not None and row["name"] == "billy"
    await database.close()


async def test_reconnecting_only_applies_new_migrations(tmp_path: Path) -> None:
    migrations = write_migrations(tmp_path / "m", "CREATE TABLE a (id INTEGER);")
    path = tmp_path / "test.db"
    first = Database(path, migrations)
    await first.connect()
    await first.close()

    write_migrations(migrations, "CREATE TABLE a (id INTEGER);", "CREATE TABLE b (id INTEGER);")
    second = Database(path, migrations)
    await second.connect()

    assert await second.schema_version() == 2
    await second.close()


async def test_failed_migration_is_rolled_back(tmp_path: Path) -> None:
    migrations = write_migrations(
        tmp_path / "m", "CREATE TABLE a (id INTEGER); INSERT INTO missing VALUES (1);"
    )
    database = Database(tmp_path / "test.db", migrations)

    with pytest.raises(Exception, match="missing"):
        await database.connect()

    assert await database.schema_version() == 0
    assert await database.fetch_all("SELECT name FROM sqlite_master WHERE name = 'a'") == []
    await database.close()


async def test_transaction_rolls_back_on_error(tmp_path: Path) -> None:
    migrations = write_migrations(tmp_path / "m", "CREATE TABLE a (id INTEGER);")
    database = Database(tmp_path / "test.db", migrations)
    await database.connect()

    with pytest.raises(RuntimeError):
        async with database.transaction() as connection:
            await connection.execute("INSERT INTO a VALUES (1)")
            raise RuntimeError("boom")

    assert await database.fetch_all("SELECT * FROM a") == []
    await database.close()


async def test_foreign_keys_are_enforced(tmp_path: Path) -> None:
    migrations = write_migrations(
        tmp_path / "m",
        "CREATE TABLE p (id INTEGER PRIMARY KEY);"
        "CREATE TABLE c (p_id INTEGER NOT NULL REFERENCES p(id));",
    )
    database = Database(tmp_path / "test.db", migrations)
    await database.connect()

    with pytest.raises(Exception, match="FOREIGN KEY"):
        await database.execute("INSERT INTO c VALUES (99)")
    await database.close()


def test_gaps_in_migration_numbers_are_rejected(tmp_path: Path) -> None:
    directory = tmp_path / "m"
    directory.mkdir()
    (directory / "0001_a.sql").write_text("")
    (directory / "0003_c.sql").write_text("")

    with pytest.raises(DatabaseError):
        discover_migrations(directory)


async def test_packaged_migrations_apply_cleanly(tmp_path: Path) -> None:
    database = Database(tmp_path / "test.db")
    await database.connect()

    assert await database.schema_version() >= 0
    await database.close()
