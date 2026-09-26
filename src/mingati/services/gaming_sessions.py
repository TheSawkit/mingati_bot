import re
from dataclasses import dataclass
from datetime import datetime, timedelta

import aiosqlite

from mingati.database import Database
from mingati.errors import UserFacingError

MIN_PLAYERS = 2
MAX_PLAYERS = 20
DEFAULT_DURATION_HOURS = 3
MAX_DURATION_HOURS = 12
TIME_PATTERN = re.compile(r"^(?P<hour>[01]?\d|2[0-3])\s*[h:]\s*(?P<minute>[0-5]\d)?$")


@dataclass(frozen=True, slots=True)
class GamingSession:
    id: int
    guild_id: int
    channel_id: int
    message_id: int | None
    host_id: int
    game: str
    platform: str
    mode: str | None
    max_players: int
    starts_at: int
    expires_at: int
    voice_channel_id: int | None
    member_ids: tuple[int, ...] = ()

    @property
    def is_full(self) -> bool:
        return len(self.member_ids) >= self.max_players


@dataclass(frozen=True, slots=True)
class NewSession:
    guild_id: int
    channel_id: int
    host_id: int
    game: str
    platform: str
    mode: str | None
    max_players: int
    starts_at: datetime
    expires_at: datetime


def clean_text(raw: str | None) -> str:
    return " ".join((raw or "").split())


def parse_start(raw: str | None, now: datetime) -> datetime:
    """Parse '21h', '21h30' or '21:30' in now's timezone; a time already passed means tomorrow."""
    if raw is None or not raw.strip() or raw.strip().lower() == "maintenant":
        return now
    match = TIME_PATTERN.match(raw.strip().lower())
    if match is None:
        raise UserFacingError("Heure invalide. Exemples : `21h`, `21h30`, `21:30`, `maintenant`.")
    start = now.replace(
        hour=int(match["hour"]), minute=int(match["minute"] or 0), second=0, microsecond=0
    )
    return start if start >= now - timedelta(minutes=5) else start + timedelta(days=1)


def plan_session(
    *,
    guild_id: int,
    channel_id: int,
    host_id: int,
    game: str,
    platform: str,
    mode: str | None,
    max_players: int,
    start: str | None,
    duration_hours: int,
    now: datetime,
) -> NewSession:
    """Validate /jouer input and compute the session time window."""
    game = clean_text(game)
    if not game:
        raise UserFacingError("Indique le jeu.")
    if not MIN_PLAYERS <= max_players <= MAX_PLAYERS:
        raise UserFacingError(
            f"Le nombre de joueurs doit être entre {MIN_PLAYERS} et {MAX_PLAYERS}."
        )
    if not 1 <= duration_hours <= MAX_DURATION_HOURS:
        raise UserFacingError(f"La durée doit être entre 1 et {MAX_DURATION_HOURS} heures.")
    starts_at = parse_start(start, now)
    return NewSession(
        guild_id=guild_id,
        channel_id=channel_id,
        host_id=host_id,
        game=game,
        platform=platform,
        mode=clean_text(mode) or None,
        max_players=max_players,
        starts_at=starts_at,
        expires_at=starts_at + timedelta(hours=duration_hours),
    )


class GamingSessionService:
    """'Qui joue ?' sessions: creation, roster changes and expiry, persisted in SQLite."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def create(self, new: NewSession, now: datetime) -> GamingSession:
        """Store a session with its host as first player; one running session per host."""
        existing = await self.database.fetch_one(
            "SELECT id FROM gaming_sessions WHERE guild_id = ? AND host_id = ? AND expires_at > ?",
            (new.guild_id, new.host_id, int(now.timestamp())),
        )
        if existing:
            raise UserFacingError(
                "Tu as déjà une session en cours. Termine-la avant d'en lancer une."
            )
        async with self.database.transaction() as connection:
            cursor = await connection.execute(
                "INSERT INTO gaming_sessions (guild_id, channel_id, host_id, game, platform, mode,"
                " max_players, starts_at, expires_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    new.guild_id,
                    new.channel_id,
                    new.host_id,
                    new.game,
                    new.platform,
                    new.mode,
                    new.max_players,
                    int(new.starts_at.timestamp()),
                    int(new.expires_at.timestamp()),
                ),
            )
            session_id = cursor.lastrowid
            await connection.execute(
                "INSERT INTO gaming_session_members (session_id, user_id) VALUES (?, ?)",
                (session_id, new.host_id),
            )
        return await self._require(session_id)

    async def attach_message(self, session_id: int, message_id: int) -> None:
        await self.database.execute(
            "UPDATE gaming_sessions SET message_id = ? WHERE id = ?", (message_id, session_id)
        )

    async def attach_voice_channel(self, session_id: int, channel_id: int) -> None:
        await self.database.execute(
            "UPDATE gaming_sessions SET voice_channel_id = ? WHERE id = ?", (channel_id, session_id)
        )

    async def get_by_message(self, message_id: int) -> GamingSession:
        row = await self.database.fetch_one(
            "SELECT id FROM gaming_sessions WHERE message_id = ?", (message_id,)
        )
        if row is None:
            raise UserFacingError("Cette session n'existe plus.")
        return await self._require(row["id"])

    async def join(self, session_id: int, user_id: int) -> GamingSession:
        async with self.database.transaction() as connection:
            row = await (
                await connection.execute(
                    "SELECT s.max_players, COUNT(m.user_id) AS players,"
                    " SUM(m.user_id = ?) AS already FROM gaming_sessions s"
                    " LEFT JOIN gaming_session_members m ON m.session_id = s.id"
                    " WHERE s.id = ? GROUP BY s.id",
                    (user_id, session_id),
                )
            ).fetchone()
            if row is None:
                raise UserFacingError("Cette session n'existe plus.")
            if row["already"]:
                raise UserFacingError("Tu fais déjà partie de cette session.")
            if row["players"] >= row["max_players"]:
                raise UserFacingError("La session est complète.")
            await connection.execute(
                "INSERT INTO gaming_session_members (session_id, user_id) VALUES (?, ?)",
                (session_id, user_id),
            )
        return await self._require(session_id)

    async def leave(self, session_id: int, user_id: int) -> GamingSession | None:
        """Remove a player; returns None when the session became empty and was deleted."""
        removed = await self.database.execute(
            "DELETE FROM gaming_session_members WHERE session_id = ? AND user_id = ?",
            (session_id, user_id),
        )
        if not removed:
            raise UserFacingError("Tu ne fais pas partie de cette session.")
        session = await self._require(session_id)
        if session.member_ids:
            return session
        await self.delete(session_id)
        return None

    async def delete(self, session_id: int) -> None:
        await self.database.execute("DELETE FROM gaming_sessions WHERE id = ?", (session_id,))

    async def pop_expired(self, now: datetime) -> list[GamingSession]:
        """Delete and return every session whose time window is over."""
        rows = await self.database.fetch_all(
            "SELECT id FROM gaming_sessions WHERE expires_at <= ?", (int(now.timestamp()),)
        )
        sessions = [await self._require(row["id"]) for row in rows]
        for session in sessions:
            await self.delete(session.id)
        return sessions

    async def remove_member_everywhere(
        self, guild_id: int, user_id: int
    ) -> list[tuple[GamingSession, GamingSession | None]]:
        """Drop a member who left the server; (before, after) pairs, after is None if deleted."""
        rows = await self.database.fetch_all(
            "SELECT s.id FROM gaming_sessions s JOIN gaming_session_members m"
            " ON m.session_id = s.id WHERE s.guild_id = ? AND m.user_id = ?",
            (guild_id, user_id),
        )
        changes = []
        for row in rows:
            before = await self._require(row["id"])
            changes.append((before, await self.leave(before.id, user_id)))
        return changes

    async def _require(self, session_id: int | None) -> GamingSession:
        row = await self.database.fetch_one(
            "SELECT * FROM gaming_sessions WHERE id = ?", (session_id,)
        )
        if row is None:
            raise UserFacingError("Cette session n'existe plus.")
        members = await self.database.fetch_all(
            "SELECT user_id FROM gaming_session_members WHERE session_id = ?"
            " ORDER BY joined_at, rowid",
            (session_id,),
        )
        return _session_from_row(row, tuple(member["user_id"] for member in members))


def _session_from_row(row: aiosqlite.Row, member_ids: tuple[int, ...]) -> GamingSession:
    return GamingSession(
        id=row["id"],
        guild_id=row["guild_id"],
        channel_id=row["channel_id"],
        message_id=row["message_id"],
        host_id=row["host_id"],
        game=row["game"],
        platform=row["platform"],
        mode=row["mode"],
        max_players=row["max_players"],
        starts_at=row["starts_at"],
        expires_at=row["expires_at"],
        voice_channel_id=row["voice_channel_id"],
        member_ids=member_ids,
    )
