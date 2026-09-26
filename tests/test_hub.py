from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from mingati.database import Database
from mingati.providers.games import FreeGame
from mingati.services.gaming_sessions import GamingSessionService, plan_session
from mingati.services.guild_config import GuildConfigStore
from mingati.views.hub import describe_free_games, describe_sessions, describe_voice_triggers

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=ZoneInfo("Europe/Brussels"))


async def test_guild_config_stores_and_overwrites_values(database: Database) -> None:
    store = GuildConfigStore(database)

    assert await store.get(1, "hub_message_id") is None
    await store.set(1, "hub_message_id", "10")
    await store.set(1, "hub_message_id", "11")

    assert await store.get(1, "hub_message_id") == "11"
    assert await store.get(2, "hub_message_id") is None


async def test_open_sessions_are_listed_with_links_and_hide_unpublished(
    database: Database,
) -> None:
    sessions = GamingSessionService(database)

    def plan(host: int, game: str) -> object:
        return plan_session(
            guild_id=1,
            channel_id=5,
            host_id=host,
            game=game,
            platform="PC",
            mode=None,
            max_players=4,
            start=None,
            duration_hours=3,
            now=NOW,
        )

    published = await sessions.create(plan(1, "Valorant"), NOW)
    await sessions.attach_message(published.id, 99)
    await sessions.create(plan(2, "Draft"), NOW)

    open_sessions = await sessions.list_open(1, NOW)
    text = describe_sessions(open_sessions, 1)

    assert [session.game for session in open_sessions] == ["Valorant"]
    assert "**Valorant** — 1/4" in text
    assert "https://discord.com/channels/1/5/99" in text
    assert await sessions.list_open(1, NOW + timedelta(hours=4)) == []


def test_empty_hub_answers_point_to_the_right_action() -> None:
    assert "/jouer" in describe_sessions([], 1)
    assert "Aucun jeu gratuit" in describe_free_games([])
    assert "configuré" in describe_voice_triggers(frozenset())


def test_free_games_and_voice_triggers_are_listed() -> None:
    game = FreeGame(
        "epic",
        "1",
        "Astrea",
        "https://store.epicgames.com/fr/p/astrea",
        ends_at=datetime(2026, 10, 1, 15, tzinfo=UTC),
    )

    assert "[Astrea](https://store.epicgames.com/fr/p/astrea) — Epic Games" in describe_free_games(
        [game]
    )
    assert describe_voice_triggers(frozenset({2, 1})).startswith("🔊 Rejoins <#1> ou <#2>")
