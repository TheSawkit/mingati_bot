from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import discord
import pytest

from mingati.database import Database
from mingati.providers.games import FreeGame
from mingati.providers.http import ProviderError
from mingati.services.free_games import FreeGameService, is_publishable

NOW = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
HTTP = object()


def epic_game(game_id: str = "1", ends_in_days: int = 3) -> FreeGame:
    return FreeGame(
        "epic",
        game_id,
        f"Epic {game_id}",
        f"https://store.epicgames.com/fr/p/{game_id}",
        starts_at=NOW - timedelta(days=1),
        ends_at=NOW + timedelta(days=ends_in_days),
    )


def steam_game(game_id: str = "10") -> FreeGame:
    return FreeGame(
        "steam", game_id, f"Steam {game_id}", f"https://store.steampowered.com/app/{game_id}/"
    )


@dataclass
class FakeProvider:
    name: str
    label: str
    games: list[FreeGame] = field(default_factory=list)
    error: Exception | None = None

    async def fetch(self, http: object) -> list[FreeGame]:
        if self.error:
            raise self.error
        return list(self.games)


@dataclass
class FakeChannel:
    announced: list[str] = field(default_factory=list)
    failing: set[str] = field(default_factory=set)

    async def publish(self, game: FreeGame) -> int:
        if game.offer_key in self.failing:
            raise discord.HTTPException(SimpleNamespace(status=500, reason="boom"), "boom")
        self.announced.append(game.title)
        return len(self.announced)


@pytest.fixture
def epic() -> FakeProvider:
    return FakeProvider("epic", "Epic Games")


@pytest.fixture
def steam() -> FakeProvider:
    return FakeProvider("steam", "Steam")


@pytest.fixture
def service(database: Database, epic: FakeProvider, steam: FakeProvider) -> FreeGameService:
    return FreeGameService(database, [epic, steam])


async def warm_up(service: FreeGameService, channel: FakeChannel) -> None:
    await service.refresh(HTTP, channel.publish, NOW)


async def test_first_run_records_current_games_without_announcing(service, epic) -> None:
    epic.games = [epic_game()]
    channel = FakeChannel()

    report = await service.refresh(HTTP, channel.publish, NOW)

    assert report.silent_first_run
    assert channel.announced == []
    assert [game.title for game in await service.active(NOW)] == ["Epic 1"]


async def test_new_game_is_announced_exactly_once(service, epic) -> None:
    channel = FakeChannel()
    epic.games = [epic_game("old")]
    await warm_up(service, channel)
    epic.games = [epic_game("old"), epic_game("new")]

    first = await service.refresh(HTTP, channel.publish, NOW)
    second = await service.refresh(HTTP, channel.publish, NOW + timedelta(hours=2))

    assert first.published == 1 and second.published == 0
    assert channel.announced == ["Epic new"]


async def test_failing_provider_does_not_block_the_others(service, epic, steam) -> None:
    channel = FakeChannel()
    await warm_up(service, channel)
    epic.error = ProviderError("Epic is down")
    steam.games = [steam_game()]

    report = await service.refresh(HTTP, channel.publish, NOW)

    assert report.errors == {"Epic Games": "Epic is down"}
    assert report.found == {"Steam": 1}
    assert channel.announced == ["Steam 10"]
    statuses = {status.name: status for status in await service.statuses()}
    assert statuses["epic"].last_error == "Epic is down"
    assert statuses["steam"].last_success_at == NOW


async def test_failed_announcement_is_retried_next_refresh(service, epic) -> None:
    channel = FakeChannel()
    await warm_up(service, channel)
    game = epic_game("new")
    epic.games = [game]
    channel.failing = {game.offer_key}

    assert (await service.refresh(HTTP, channel.publish, NOW)).published == 0
    channel.failing = set()
    assert (await service.refresh(HTTP, channel.publish, NOW)).published == 1
    assert channel.announced == ["Epic new"]


async def test_same_game_offered_again_later_is_announced_again(service, epic) -> None:
    channel = FakeChannel()
    await warm_up(service, channel)
    epic.games = [epic_game("42", ends_in_days=3)]
    await service.refresh(HTTP, channel.publish, NOW)
    epic.games = [epic_game("42", ends_in_days=90)]

    await service.refresh(HTTP, channel.publish, NOW)

    assert channel.announced == ["Epic 42", "Epic 42"]


async def test_open_ended_offer_can_come_back_after_disappearing(service, steam) -> None:
    channel = FakeChannel()
    await warm_up(service, channel)
    steam.games = [steam_game()]
    await service.refresh(HTTP, channel.publish, NOW)
    steam.games = []
    await service.refresh(HTTP, channel.publish, NOW)
    steam.games = [steam_game()]

    await service.refresh(HTTP, channel.publish, NOW)

    assert channel.announced == ["Steam 10", "Steam 10"]


async def test_last_success_is_the_latest_provider_success(service) -> None:
    assert await service.last_success() is None

    await warm_up(service, FakeChannel())

    assert await service.last_success() == NOW


@pytest.mark.parametrize(
    "game",
    [
        FreeGame("epic", "1", "  ", "https://x"),
        FreeGame("epic", "1", "Game", "http://insecure"),
        FreeGame("epic", "1", "Game", "https://x", ends_at=NOW - timedelta(minutes=1)),
    ],
)
def test_unusable_offers_are_rejected(game: FreeGame) -> None:
    assert not is_publishable(game, NOW)


async def test_game_appearing_after_an_empty_first_run_is_announced(service, epic) -> None:
    channel = FakeChannel()
    await warm_up(service, channel)
    epic.games = [epic_game("later")]

    await service.refresh(HTTP, channel.publish, NOW)

    assert channel.announced == ["Epic later"]


async def test_source_that_failed_on_first_run_stays_silent_on_its_first_success(
    service, epic
) -> None:
    channel = FakeChannel()
    epic.error = ProviderError("down")
    await warm_up(service, channel)
    epic.error = None
    epic.games = [epic_game("already-free")]

    report = await service.refresh(HTTP, channel.publish, NOW)

    assert report.silent_first_run
    assert channel.announced == []
