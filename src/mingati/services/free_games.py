import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import aiohttp
import aiosqlite
import discord

from mingati.database import Database
from mingati.providers.games import FreeGame, GameProvider

log = logging.getLogger(__name__)

KEEP_ENDED_OFFERS = timedelta(days=30)
MAX_TITLE_LENGTH = 256

Publisher = Callable[[FreeGame], Awaitable[int]]


@dataclass(frozen=True, slots=True)
class SourceStatus:
    name: str
    label: str
    last_success_at: datetime | None
    last_count: int
    last_error: str | None
    last_error_at: datetime | None


@dataclass(slots=True)
class RefreshReport:
    found: dict[str, int] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    published: int = 0
    silent_first_run: bool = False


def is_publishable(game: FreeGame, now: datetime) -> bool:
    """Reject offers that are already over or carry unusable data."""
    return (
        bool(game.title.strip())
        and len(game.title) <= MAX_TITLE_LENGTH
        and game.url.startswith("https://")
        and (game.ends_at is None or game.ends_at > now)
    )


def _timestamp(value: datetime | None) -> int | None:
    return int(value.timestamp()) if value else None


def _datetime(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value is not None else None


def _game_from_row(row: aiosqlite.Row) -> FreeGame:
    return FreeGame(
        source=row["source"],
        external_id=row["external_id"],
        title=row["title"],
        url=row["url"],
        image_url=row["image_url"],
        starts_at=_datetime(row["starts_at"]),
        ends_at=_datetime(row["ends_at"]),
    )


class FreeGameService:
    """Free games pipeline: fetch every provider, keep new valid offers, announce them once."""

    def __init__(self, database: Database, providers: Sequence[GameProvider]) -> None:
        self.database = database
        self.providers = list(providers)
        self._refreshing = asyncio.Lock()

    async def refresh(
        self, http: aiohttp.ClientSession, publish: Publisher, now: datetime
    ) -> RefreshReport:
        """Run the whole pipeline; one failing provider never blocks the others."""
        async with self._refreshing:
            report = RefreshReport()
            results = await asyncio.gather(
                *(provider.fetch(http) for provider in self.providers), return_exceptions=True
            )
            for provider, result in zip(self.providers, results, strict=True):
                if isinstance(result, BaseException):
                    log.warning("Free games source %s failed: %s", provider.name, result)
                    report.errors[provider.label] = str(result) or type(result).__name__
                    await self._record_failure(provider.name, report.errors[provider.label], now)
                    continue
                games = [game for game in result if is_publishable(game, now)]
                silent = not await self._has_succeeded(provider.name)
                report.silent_first_run |= silent
                await self._store(provider.name, games, silent, now)
                await self._record_success(provider.name, len(games), now)
                report.found[provider.label] = len(games)

            report.published = await self._publish_pending(publish, now)
            await self.database.execute(
                "DELETE FROM free_games WHERE ends_at < ?",
                (_timestamp(now - KEEP_ENDED_OFFERS),),
            )
            return report

    async def active(self, now: datetime) -> list[FreeGame]:
        """Offers announced and still running, for status displays."""
        rows = await self.database.fetch_all(
            "SELECT * FROM free_games WHERE published_at IS NOT NULL"
            " AND (ends_at IS NULL OR ends_at > ?) ORDER BY first_seen_at",
            (_timestamp(now),),
        )
        return [_game_from_row(row) for row in rows]

    async def statuses(self) -> list[SourceStatus]:
        rows = await self.database.fetch_all("SELECT * FROM game_sources")
        by_name = {row["name"]: row for row in rows}
        statuses = []
        for provider in self.providers:
            row = by_name.get(provider.name)
            statuses.append(
                SourceStatus(
                    name=provider.name,
                    label=provider.label,
                    last_success_at=_datetime(row["last_success_at"]) if row else None,
                    last_count=row["last_count"] if row else 0,
                    last_error=row["last_error"] if row else None,
                    last_error_at=_datetime(row["last_error_at"]) if row else None,
                )
            )
        return statuses

    async def last_success(self) -> datetime | None:
        row = await self.database.fetch_one("SELECT MAX(last_success_at) FROM game_sources")
        return _datetime(row[0]) if row else None

    async def _has_succeeded(self, source: str) -> bool:
        row = await self.database.fetch_one(
            "SELECT last_success_at FROM game_sources WHERE name = ?", (source,)
        )
        return bool(row and row["last_success_at"] is not None)

    async def _store(self, source: str, games: list[FreeGame], silent: bool, now: datetime) -> None:
        published_at = _timestamp(now) if silent else None
        async with self.database.transaction() as connection:
            await connection.executemany(
                "INSERT OR IGNORE INTO free_games (source, external_id, title, url, image_url,"
                " starts_at, ends_at, offer_key, published_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        game.source,
                        game.external_id,
                        game.title,
                        game.url,
                        game.image_url,
                        _timestamp(game.starts_at),
                        _timestamp(game.ends_at),
                        game.offer_key,
                        published_at,
                    )
                    for game in games
                ],
            )
            current = [game.offer_key for game in games]
            placeholders = ",".join("?" * len(current))
            await connection.execute(
                "DELETE FROM free_games WHERE source = ? AND ends_at IS NULL"
                f" AND offer_key NOT IN ({placeholders})",
                (source, *current),
            )

    async def _publish_pending(self, publish: Publisher, now: datetime) -> int:
        rows = await self.database.fetch_all(
            "SELECT * FROM free_games WHERE published_at IS NULL"
            " AND (ends_at IS NULL OR ends_at > ?) ORDER BY first_seen_at",
            (_timestamp(now),),
        )
        published = 0
        for row in rows:
            game = _game_from_row(row)
            try:
                message_id = await publish(game)
            except discord.HTTPException:
                log.warning(
                    "Could not announce free game %s, will retry", game.offer_key, exc_info=True
                )
                continue
            await self.database.execute(
                "UPDATE free_games SET published_at = ?, message_id = ? WHERE id = ?",
                (_timestamp(now), message_id, row["id"]),
            )
            published += 1
        return published

    async def _record_success(self, source: str, count: int, now: datetime) -> None:
        await self.database.execute(
            "INSERT INTO game_sources (name, last_success_at, last_count) VALUES (?, ?, ?)"
            " ON CONFLICT (name) DO UPDATE SET last_success_at = excluded.last_success_at,"
            " last_count = excluded.last_count",
            (source, _timestamp(now), count),
        )

    async def _record_failure(self, source: str, error: str, now: datetime) -> None:
        await self.database.execute(
            "INSERT INTO game_sources (name, last_error, last_error_at) VALUES (?, ?, ?)"
            " ON CONFLICT (name) DO UPDATE SET last_error = excluded.last_error,"
            " last_error_at = excluded.last_error_at",
            (source, error[:500], _timestamp(now)),
        )
