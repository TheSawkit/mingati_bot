import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.services.gaming_sessions import (
    GamingSessionService,
    NewSession,
    parse_start,
    plan_session,
)
from mingati.views.gaming import build_session_embed

BRUSSELS = ZoneInfo("Europe/Brussels")
NOW = datetime(2026, 9, 26, 20, 0, tzinfo=BRUSSELS)
GUILD = 1
HOST = 10


@pytest.fixture
def service(database: Database) -> GamingSessionService:
    return GamingSessionService(database)


def planned(host: int = HOST, max_players: int = 3, **overrides) -> NewSession:
    options = {
        "guild_id": GUILD,
        "channel_id": 2,
        "host_id": host,
        "game": "Cyberpunk 2077",
        "platform": "PC",
        "mode": None,
        "max_players": max_players,
        "start": None,
        "duration_hours": 3,
        "now": NOW,
    } | overrides
    return plan_session(**options)


async def test_host_is_the_first_player(service: GamingSessionService) -> None:
    session = await service.create(planned(), NOW)

    assert session.member_ids == (HOST,)
    assert session.expires_at == int((NOW + timedelta(hours=3)).timestamp())


async def test_players_join_in_order_until_full(service: GamingSessionService) -> None:
    session = await service.create(planned(max_players=3), NOW)

    await service.join(session.id, 11)
    full = await service.join(session.id, 12)

    assert full.member_ids == (HOST, 11, 12)
    assert full.is_full
    with pytest.raises(UserFacingError, match="complète"):
        await service.join(session.id, 13)


async def test_double_join_is_refused(service: GamingSessionService) -> None:
    session = await service.create(planned(), NOW)

    with pytest.raises(UserFacingError, match="déjà partie"):
        await service.join(session.id, HOST)


async def test_concurrent_joins_never_exceed_the_maximum(service: GamingSessionService) -> None:
    session = await service.create(planned(max_players=3), NOW)

    results = await asyncio.gather(
        *(service.join(session.id, user_id) for user_id in range(20, 30)), return_exceptions=True
    )

    assert sum(not isinstance(result, Exception) for result in results) == 2
    await service.attach_message(session.id, 777)
    assert len((await service.get_by_message(777)).member_ids) == 3


async def test_leaving_updates_roster_and_last_leave_deletes(service: GamingSessionService) -> None:
    session = await service.create(planned(), NOW)
    await service.join(session.id, 11)

    after_host_left = await service.leave(session.id, HOST)
    assert after_host_left is not None and after_host_left.member_ids == (11,)

    assert await service.leave(session.id, 11) is None
    with pytest.raises(UserFacingError, match="n'existe plus"):
        await service.join(session.id, 12)


async def test_leaving_a_session_you_are_not_in_is_refused(service: GamingSessionService) -> None:
    session = await service.create(planned(), NOW)

    with pytest.raises(UserFacingError, match="pas partie"):
        await service.leave(session.id, 99)


async def test_one_running_session_per_host(service: GamingSessionService) -> None:
    await service.create(planned(), NOW)

    with pytest.raises(UserFacingError, match="déjà une session"):
        await service.create(planned(), NOW)

    await service.create(planned(), NOW + timedelta(hours=4))


async def test_expired_sessions_are_removed(service: GamingSessionService) -> None:
    short = await service.create(planned(host=1, duration_hours=1), NOW)
    long = await service.create(planned(host=2, duration_hours=5), NOW)

    expired = await service.pop_expired((NOW + timedelta(hours=2)).astimezone(UTC))

    assert [session.id for session in expired] == [short.id]
    assert await service.pop_expired(NOW + timedelta(hours=2)) == []
    await service.attach_message(long.id, 555)
    assert (await service.get_by_message(555)).id == long.id


async def test_member_leaving_the_server_is_removed_everywhere(
    service: GamingSessionService,
) -> None:
    shared = await service.create(planned(host=1), NOW)
    await service.join(shared.id, 42)
    solo = await service.create(planned(host=42), NOW)

    changes = await service.remove_member_everywhere(GUILD, 42)

    after = {before.id: result for before, result in changes}
    assert after[shared.id].member_ids == (1,)
    assert after[solo.id] is None


async def test_card_lists_players_and_marks_full_sessions(service: GamingSessionService) -> None:
    session = await service.create(planned(max_players=2, mode="Ranked"), NOW)
    full = await service.join(session.id, 11)

    embed = build_session_embed(full)

    assert embed.title == "🎮 Cyberpunk 2077"
    assert "👥 **2 / 2** — **Complet**" in embed.description
    assert f"<@{HOST}> 👑" in embed.description
    assert "<@11>" in embed.description
    assert "🎯 Ranked" in embed.description


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, NOW),
        ("maintenant", NOW),
        ("21h", NOW.replace(hour=21)),
        ("21h30", NOW.replace(hour=21, minute=30)),
        ("21:30", NOW.replace(hour=21, minute=30)),
        ("19h58", NOW.replace(hour=19, minute=58)),
        ("8h", NOW.replace(hour=8) + timedelta(days=1)),
    ],
)
def test_parse_start(raw: str | None, expected: datetime) -> None:
    assert parse_start(raw, NOW) == expected


@pytest.mark.parametrize("raw", ["25h", "demain", "21h75"])
def test_parse_start_rejects_garbage(raw: str) -> None:
    with pytest.raises(UserFacingError, match="Heure invalide"):
        parse_start(raw, NOW)


def test_plan_session_normalises_text() -> None:
    session = planned(game="  Rocket   League ", mode="   ")

    assert session.game == "Rocket League"
    assert session.mode is None


async def test_deleted_voice_room_is_unlinked_from_its_session(
    service: GamingSessionService,
) -> None:
    session = await service.create(planned(), NOW)
    await service.attach_voice_channel(session.id, 555)

    unlinked = await service.detach_voice_channel(555)

    assert [s.id for s in unlinked] == [session.id]
    assert unlinked[0].voice_channel_id is None
    assert "<#555>" not in build_session_embed(unlinked[0]).description
    assert await service.detach_voice_channel(555) == []
