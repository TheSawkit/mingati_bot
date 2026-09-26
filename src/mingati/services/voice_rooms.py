import asyncio
import logging
import random
from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import TypeGuard

import aiosqlite
import discord

from mingati.database import Database
from mingati.errors import UserFacingError

log = logging.getLogger(__name__)

MAX_NAME_LENGTH = 100
MAX_USER_LIMIT = 99
RENAME_TIMEOUT_SECONDS = 10


@dataclass(frozen=True, slots=True)
class VoiceRoom:
    channel_id: int
    guild_id: int
    owner_id: int
    trigger_channel_id: int
    panel_message_id: int | None = None
    is_locked: bool = False

    @classmethod
    def from_row(cls, row: aiosqlite.Row) -> "VoiceRoom":
        return cls(
            channel_id=row["channel_id"],
            guild_id=row["guild_id"],
            owner_id=row["owner_id"],
            trigger_channel_id=row["trigger_channel_id"],
            panel_message_id=row["panel_message_id"],
            is_locked=bool(row["is_locked"]),
        )


@dataclass(slots=True)
class ReconcileReport:
    removed: int = 0
    transferred: list[VoiceRoom] = field(default_factory=list)
    created: list[VoiceRoom] = field(default_factory=list)


def is_voice_channel(channel: object) -> TypeGuard[discord.VoiceChannel]:
    """Voice (not stage, not text) channel check that also accepts test doubles."""
    return getattr(channel, "type", None) == discord.ChannelType.voice


def room_name(display_name: str) -> str:
    """Default name of a member's temporary room, clipped to Discord's channel name limit."""
    return f"{display_name}'s Palace"[:MAX_NAME_LENGTH]


def humans(members: Iterable[discord.Member]) -> list[discord.Member]:
    return [member for member in members if not member.bot]


def successor_candidates(
    members: Sequence[discord.Member], rng: random.Random | None = None
) -> list[discord.Member]:
    """Remaining humans in random order, to hand over a room whose owner left (issue #1)."""
    candidates = humans(members)
    (rng or random).shuffle(candidates)
    return candidates


def validate_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise UserFacingError("Le nom ne peut pas être vide.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise UserFacingError(f"Le nom doit faire au maximum {MAX_NAME_LENGTH} caractères.")
    return cleaned


def validate_limit(limit: int) -> int:
    if not 0 <= limit <= MAX_USER_LIMIT:
        raise UserFacingError(f"La limite doit être entre 0 (illimité) et {MAX_USER_LIMIT}.")
    return limit


def copy_overwrite(overwrite: discord.PermissionOverwrite) -> discord.PermissionOverwrite:
    return discord.PermissionOverwrite.from_pair(*overwrite.pair())


def inherited_overwrites[T: Hashable](
    category_overwrites: Mapping[T, discord.PermissionOverwrite],
) -> dict[T, discord.PermissionOverwrite]:
    """Category overwrites without Manage Roles, which only administrators may set on creation."""
    copied = {
        target: copy_overwrite(overwrite) for target, overwrite in category_overwrites.items()
    }
    for overwrite in copied.values():
        overwrite.manage_roles = None
    return copied


def with_member_access[T: Hashable](
    overwrites: Mapping[T, discord.PermissionOverwrite], members: Iterable[T]
) -> dict[T, discord.PermissionOverwrite]:
    """Overwrites granting the given members the right to see and join the room."""
    updated = {target: copy_overwrite(overwrite) for target, overwrite in overwrites.items()}
    for member in members:
        overwrite = updated.get(member) or discord.PermissionOverwrite()
        overwrite.update(view_channel=True, connect=True)
        updated[member] = overwrite
    return updated


def locked_overwrites[T: Hashable](
    overwrites: Mapping[T, discord.PermissionOverwrite], roles: Iterable[T], allowed: Iterable[T]
) -> dict[T, discord.PermissionOverwrite]:
    """Deny Connect to every role (a role allow beats @everyone deny), allow listed members."""
    updated = {target: copy_overwrite(overwrite) for target, overwrite in overwrites.items()}
    for role in roles:
        overwrite = updated.get(role) or discord.PermissionOverwrite()
        overwrite.connect = False
        updated[role] = overwrite
    return with_member_access(updated, allowed)


def unlocked_overwrites[T: Hashable](
    overwrites: Mapping[T, discord.PermissionOverwrite],
    roles: Iterable[T],
    category_overwrites: Mapping[T, discord.PermissionOverwrite],
) -> dict[T, discord.PermissionOverwrite]:
    """Restore each role's Connect to the category's value, keeping member grants."""
    updated = {target: copy_overwrite(overwrite) for target, overwrite in overwrites.items()}
    for role in roles:
        overwrite = updated.get(role) or discord.PermissionOverwrite()
        source = category_overwrites.get(role)
        overwrite.connect = source.connect if source else None
        if overwrite.is_empty():
            updated.pop(role, None)
        else:
            updated[role] = overwrite
    return updated


class VoiceRoomStore:
    """SQLite persistence of temporary voice rooms."""

    def __init__(self, database: Database) -> None:
        self.database = database

    async def get(self, channel_id: int) -> VoiceRoom | None:
        row = await self.database.fetch_one(
            "SELECT * FROM temporary_voice_channels WHERE channel_id = ?", (channel_id,)
        )
        return VoiceRoom.from_row(row) if row else None

    async def get_by_owner(self, guild_id: int, owner_id: int) -> VoiceRoom | None:
        row = await self.database.fetch_one(
            "SELECT * FROM temporary_voice_channels WHERE guild_id = ? AND owner_id = ?",
            (guild_id, owner_id),
        )
        return VoiceRoom.from_row(row) if row else None

    async def list(self, guild_id: int) -> list[VoiceRoom]:
        rows = await self.database.fetch_all(
            "SELECT * FROM temporary_voice_channels WHERE guild_id = ?", (guild_id,)
        )
        return [VoiceRoom.from_row(row) for row in rows]

    async def add(self, room: VoiceRoom) -> None:
        await self.database.execute(
            "INSERT INTO temporary_voice_channels"
            " (channel_id, guild_id, owner_id, trigger_channel_id) VALUES (?, ?, ?, ?)",
            (room.channel_id, room.guild_id, room.owner_id, room.trigger_channel_id),
        )

    async def delete(self, channel_id: int) -> bool:
        deleted = await self.database.execute(
            "DELETE FROM temporary_voice_channels WHERE channel_id = ?", (channel_id,)
        )
        return deleted > 0

    async def set_owner(self, channel_id: int, owner_id: int) -> None:
        try:
            await self.database.execute(
                "UPDATE temporary_voice_channels SET owner_id = ? WHERE channel_id = ?",
                (owner_id, channel_id),
            )
        except aiosqlite.IntegrityError as error:
            raise UserFacingError("Cette personne a déjà son propre salon vocal.") from error

    async def set_locked(self, channel_id: int, locked: bool) -> None:
        await self.database.execute(
            "UPDATE temporary_voice_channels SET is_locked = ? WHERE channel_id = ?",
            (int(locked), channel_id),
        )

    async def set_panel_message(self, channel_id: int, message_id: int) -> None:
        await self.database.execute(
            "UPDATE temporary_voice_channels SET panel_message_id = ? WHERE channel_id = ?",
            (message_id, channel_id),
        )


class VoiceRoomService:
    """Lifecycle and owner controls of temporary voice rooms created from trigger channels."""

    def __init__(self, store: VoiceRoomStore, trigger_ids: frozenset[int]) -> None:
        self.store = store
        self.trigger_ids = trigger_ids
        self._lifecycle = asyncio.Lock()

    def is_trigger(self, channel_id: int) -> bool:
        return channel_id in self.trigger_ids

    async def on_trigger_join(
        self, member: discord.Member, trigger: discord.VoiceChannel
    ) -> VoiceRoom | None:
        """Create the member's room and move them in; returns the room only when newly created."""
        async with self._lifecycle:
            return await self._open_room(member, trigger)

    async def on_leave(
        self, member: discord.Member, channel: discord.VoiceChannel
    ) -> VoiceRoom | None:
        """Delete the room once empty or hand it over; returns the room if its owner changed."""
        async with self._lifecycle:
            room = await self.store.get(channel.id)
            if room is None:
                return None
            if not humans(channel.members):
                await self._delete(channel)
                return None
            if room.owner_id == member.id:
                return await self._transfer_to_successor(room, channel)
            return None

    async def forget(self, channel_id: int) -> None:
        if await self.store.delete(channel_id):
            log.info("Temporary voice room %s was deleted outside the bot", channel_id)

    async def reconcile(self, guild: discord.Guild) -> ReconcileReport:
        """Repair state after downtime: drop dead rooms, fix owners, serve waiting members."""
        report = ReconcileReport()
        async with self._lifecycle:
            for room in await self.store.list(guild.id):
                channel = guild.get_channel(room.channel_id)
                if not is_voice_channel(channel):
                    await self.store.delete(room.channel_id)
                    report.removed += 1
                elif not humans(channel.members):
                    await self._delete(channel)
                    report.removed += 1
                elif room.owner_id not in {member.id for member in channel.members}:
                    new_room = await self._transfer_to_successor(room, channel)
                    if new_room:
                        report.transferred.append(new_room)

            for trigger_id in self.trigger_ids:
                trigger = guild.get_channel(trigger_id)
                if not is_voice_channel(trigger):
                    log.warning("Voice trigger channel %s not found in guild", trigger_id)
                    continue
                for member in humans(trigger.members):
                    created = await self._open_room(member, trigger)
                    if created:
                        report.created.append(created)
        return report

    async def require_owned_room(self, actor: discord.Member, channel_id: int) -> VoiceRoom:
        room = await self.store.get(channel_id)
        if room is None:
            raise UserFacingError("Ce salon n'est pas un vocal temporaire.")
        if room.owner_id != actor.id:
            raise UserFacingError("Seul le propriétaire du salon peut faire ça.")
        return room

    async def rename(self, actor: discord.Member, channel: discord.VoiceChannel, name: str) -> str:
        await self.require_owned_room(actor, channel.id)
        cleaned = validate_name(name)
        try:
            await asyncio.wait_for(channel.edit(name=cleaned), RENAME_TIMEOUT_SECONDS)
        except TimeoutError as error:
            raise UserFacingError(
                "Discord limite les renommages de salon. Réessaie dans quelques minutes."
            ) from error
        return cleaned

    async def set_limit(
        self, actor: discord.Member, channel: discord.VoiceChannel, limit: int
    ) -> int:
        await self.require_owned_room(actor, channel.id)
        await channel.edit(user_limit=validate_limit(limit))
        return limit

    async def lock(self, actor: discord.Member, channel: discord.VoiceChannel) -> VoiceRoom:
        room = await self.require_owned_room(actor, channel.id)
        allowed = [actor, *humans(channel.members)]
        await channel.edit(
            overwrites=locked_overwrites(channel.overwrites, self._roles(channel), allowed)
        )
        await self.store.set_locked(channel.id, True)
        return replace(room, is_locked=True)

    async def unlock(self, actor: discord.Member, channel: discord.VoiceChannel) -> VoiceRoom:
        room = await self.require_owned_room(actor, channel.id)
        category_overwrites = channel.category.overwrites if channel.category else {}
        await channel.edit(
            overwrites=unlocked_overwrites(
                channel.overwrites, self._roles(channel), category_overwrites
            )
        )
        await self.store.set_locked(channel.id, False)
        return replace(room, is_locked=False)

    async def invite(
        self, actor: discord.Member, channel: discord.VoiceChannel, guest: discord.Member
    ) -> None:
        await self.require_owned_room(actor, channel.id)
        if guest.bot:
            raise UserFacingError("Inutile d'inviter un bot.")
        await channel.edit(overwrites=with_member_access(channel.overwrites, [guest]))

    async def transfer(
        self, actor: discord.Member, channel: discord.VoiceChannel, new_owner: discord.Member
    ) -> VoiceRoom:
        room = await self.require_owned_room(actor, channel.id)
        if new_owner.id == actor.id:
            raise UserFacingError("Tu es déjà le propriétaire.")
        if new_owner.bot or new_owner not in channel.members:
            raise UserFacingError("Le nouveau propriétaire doit être dans le salon.")
        async with self._lifecycle:
            return await self._assign_owner(room, channel, new_owner)

    async def close(self, actor: discord.Member, channel: discord.VoiceChannel) -> None:
        await self.require_owned_room(actor, channel.id)
        async with self._lifecycle:
            await self._delete(channel)

    async def _open_room(
        self, member: discord.Member, trigger: discord.VoiceChannel
    ) -> VoiceRoom | None:
        if member.voice is None or member.voice.channel != trigger:
            return None
        existing = await self.store.get_by_owner(member.guild.id, member.id)
        if existing:
            channel = member.guild.get_channel(existing.channel_id)
            if is_voice_channel(channel):
                await self._move_or_cleanup(member, channel)
                return None
            await self.store.delete(existing.channel_id)

        channel = await self._create_channel(member, trigger)
        room = VoiceRoom(
            channel_id=channel.id,
            guild_id=member.guild.id,
            owner_id=member.id,
            trigger_channel_id=trigger.id,
        )
        await self.store.add(room)
        log.info("Created temporary voice room %s for member %s", channel.id, member.id)
        return room if await self._move_or_cleanup(member, channel) else None

    async def _create_channel(
        self, member: discord.Member, trigger: discord.VoiceChannel
    ) -> discord.VoiceChannel:
        guild = member.guild
        category = trigger.category
        base = inherited_overwrites(category.overwrites) if category else {}
        options = {"name": room_name(member.display_name), "category": category}
        bitrate = int(guild.bitrate_limit)
        try:
            return await guild.create_voice_channel(
                **options, bitrate=bitrate, overwrites=with_member_access(base, [member])
            )
        except discord.Forbidden:
            log.warning("Cannot copy category overwrites, creating room with inherited defaults")
            return await guild.create_voice_channel(**options, bitrate=bitrate)

    async def _move_or_cleanup(self, member: discord.Member, channel: discord.VoiceChannel) -> bool:
        try:
            await member.move_to(channel)
        except discord.HTTPException:
            log.info("Member %s left before being moved to room %s", member.id, channel.id)
            if not humans(channel.members):
                await self._delete(channel)
            return False
        return True

    async def _transfer_to_successor(
        self, room: VoiceRoom, channel: discord.VoiceChannel
    ) -> VoiceRoom | None:
        for successor in successor_candidates(channel.members):
            try:
                return await self._assign_owner(room, channel, successor)
            except UserFacingError:
                log.info("Member %s already owns a room, trying another successor", successor.id)
        return None

    async def _assign_owner(
        self, room: VoiceRoom, channel: discord.VoiceChannel, new_owner: discord.Member
    ) -> VoiceRoom:
        await self.store.set_owner(channel.id, new_owner.id)
        if room.is_locked:
            await channel.edit(overwrites=with_member_access(channel.overwrites, [new_owner]))
        log.info("Room %s now belongs to member %s", channel.id, new_owner.id)
        return replace(room, owner_id=new_owner.id)

    async def _delete(self, channel: discord.VoiceChannel) -> None:
        try:
            await channel.delete(reason="Salon vocal temporaire")
        except discord.NotFound:
            log.debug("Room %s was already gone", channel.id)
        await self.store.delete(channel.id)
        log.info("Deleted temporary voice room %s", channel.id)

    @staticmethod
    def _roles(channel: discord.VoiceChannel) -> list[discord.Role | discord.Object]:
        roles = [target for target in channel.overwrites if isinstance(target, discord.Role)]
        default_role = channel.guild.default_role
        return roles if default_role in roles else [default_role, *roles]
