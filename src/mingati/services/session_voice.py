from dataclasses import dataclass, field, replace

import discord

from mingati.errors import UserFacingError
from mingati.services.gaming_sessions import GamingSession, GamingSessionService
from mingati.services.voice_rooms import VoiceRoom, VoiceRoomService


@dataclass(frozen=True, slots=True)
class SessionVoice:
    session: GamingSession
    channel_id: int
    already_open: bool = False
    created_room: VoiceRoom | None = None
    guests: list[discord.abc.Snowflake] = field(default_factory=list)


async def open_session_voice(
    sessions: GamingSessionService,
    voice_rooms: VoiceRoomService,
    session: GamingSession,
    actor: discord.Member,
    trigger: discord.VoiceChannel | None,
) -> SessionVoice:
    """Give a gaming session its voice room: players only, reused when it already exists."""
    if actor.id not in session.member_ids:
        raise UserFacingError("Rejoins la session avant de créer son vocal.")
    existing = actor.guild.get_channel(session.voice_channel_id or 0)
    if isinstance(existing, discord.VoiceChannel):
        return SessionVoice(session, session.voice_channel_id, already_open=True)
    if trigger is None:
        raise UserFacingError("Aucun salon « Créer un vocal » gaming n'est configuré.")

    guests = [
        actor.guild.get_member(user_id) or discord.Object(user_id)
        for user_id in session.member_ids
        if user_id != actor.id
    ]
    room, created = await voice_rooms.open_session_room(
        actor, trigger, f"🎮 {session.game}", guests, session.max_players
    )
    await sessions.attach_voice_channel(session.id, room.channel_id)
    return SessionVoice(
        session=replace(session, voice_channel_id=room.channel_id),
        channel_id=room.channel_id,
        created_room=room if created else None,
        guests=guests,
    )
