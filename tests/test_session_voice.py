from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import discord
import pytest

from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.services.gaming_sessions import GamingSessionService, plan_session
from mingati.services.session_voice import open_session_voice
from mingati.services.voice_rooms import VoiceRoomService, VoiceRoomStore

from fakes import FakeCategory, FakeGuild

NOW = datetime(2026, 9, 26, 20, 0, tzinfo=ZoneInfo("Europe/Brussels"))


@pytest.fixture
async def context(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    guild = FakeGuild()
    trigger = guild.add_voice_channel("CRÉER UN VOCAL", FakeCategory())
    sessions = GamingSessionService(database)
    voice_rooms = VoiceRoomService(VoiceRoomStore(database), frozenset({trigger.id}))
    host = guild.add_member("Alice")
    session = await sessions.create(
        plan_session(
            guild_id=guild.id,
            channel_id=1,
            host_id=host.id,
            game="Valorant",
            platform="PC",
            mode=None,
            max_players=5,
            start=None,
            duration_hours=3,
            now=NOW,
        ),
        NOW,
    )
    session = await sessions.join(session.id, 4242)
    yield guild, trigger, sessions, voice_rooms, host, session
    await database.close()


async def test_player_opens_a_room_shared_with_the_other_players(context) -> None:
    guild, trigger, sessions, voice_rooms, host, session = context

    result = await open_session_voice(sessions, voice_rooms, session, host, trigger)

    channel = guild.get_channel(result.channel_id)
    assert result.created_room is not None
    assert result.session.voice_channel_id == result.channel_id
    assert channel.overwrites[discord.Object(4242)].connect is True
    assert [guest.id for guest in result.guests] == [4242]


async def test_existing_room_is_reused(context) -> None:
    guild, trigger, sessions, voice_rooms, host, session = context
    first = await open_session_voice(sessions, voice_rooms, session, host, trigger)

    again = await open_session_voice(sessions, voice_rooms, first.session, host, trigger)

    assert again.already_open
    assert again.channel_id == first.channel_id
    assert len(guild.created) == 1


async def test_only_players_can_open_the_room(context) -> None:
    guild, trigger, sessions, voice_rooms, _, session = context

    with pytest.raises(UserFacingError, match="Rejoins la session"):
        await open_session_voice(
            sessions, voice_rooms, session, guild.add_member("Intrus"), trigger
        )


async def test_missing_gaming_trigger_is_explained(context) -> None:
    _, _, sessions, voice_rooms, host, session = context

    with pytest.raises(UserFacingError, match="gaming n'est configuré"):
        await open_session_voice(sessions, voice_rooms, session, host, None)
