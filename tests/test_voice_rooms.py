import asyncio
import random
from pathlib import Path

import discord
import pytest

from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.services.voice_rooms import (
    VoiceRoom,
    VoiceRoomService,
    VoiceRoomStore,
    inherited_overwrites,
    locked_overwrites,
    room_name,
    successor_candidates,
    unlocked_overwrites,
    validate_limit,
    validate_name,
)

from fakes import FakeCategory, FakeGuild, FakeVoiceChannel


@pytest.fixture
async def database(tmp_path: Path):
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()


@pytest.fixture
def guild() -> FakeGuild:
    return FakeGuild()


@pytest.fixture
def category(guild: FakeGuild) -> FakeCategory:
    return FakeCategory(
        overwrites={
            guild.default_role: discord.PermissionOverwrite(view_channel=True, connect=True)
        }
    )


@pytest.fixture
def trigger(guild: FakeGuild, category: FakeCategory) -> FakeVoiceChannel:
    return guild.add_voice_channel("CRÉER UN VOCAL", category)


@pytest.fixture
def service(database: Database, trigger: FakeVoiceChannel) -> VoiceRoomService:
    return VoiceRoomService(VoiceRoomStore(database), frozenset({trigger.id}))


async def open_room(service, guild, trigger, name="Alice"):
    member = guild.add_member(name)
    member.connect_to(trigger)
    room = await service.on_trigger_join(member, trigger)
    return member, room, guild.get_channel(room.channel_id) if room else None


async def test_joining_trigger_creates_owned_room_in_same_category(
    service, guild, trigger, category
) -> None:
    member, room, channel = await open_room(service, guild, trigger)

    assert channel is not None
    assert channel.category is category
    assert channel.name == "Alice's Palace"
    assert channel.bitrate == 96000
    assert member.voice.channel is channel
    assert room.owner_id == member.id
    assert await service.store.get(channel.id) == room
    assert channel.overwrites[member].connect is True
    assert channel.overwrites[guild.default_role].connect is True


async def test_member_with_a_room_is_moved_back_instead_of_getting_a_second_one(
    service, guild, trigger
) -> None:
    member, _, channel = await open_room(service, guild, trigger)
    member.connect_to(trigger)

    assert await service.on_trigger_join(member, trigger) is None

    assert len(guild.created) == 1
    assert member.voice.channel is channel


async def test_concurrent_voice_events_create_a_single_room(service, guild, trigger) -> None:
    member = guild.add_member("Alice")
    member.connect_to(trigger)

    await asyncio.gather(*(service.on_trigger_join(member, trigger) for _ in range(3)))

    assert len(guild.created) == 1


async def test_member_who_already_left_the_trigger_gets_nothing(service, guild, trigger) -> None:
    member = guild.add_member("Alice")

    assert await service.on_trigger_join(member, trigger) is None
    assert guild.created == []


async def test_failed_move_deletes_the_fresh_room(service, guild, trigger) -> None:
    member = guild.add_member("Alice")
    member.connect_to(trigger)
    member.fail_move = True

    assert await service.on_trigger_join(member, trigger) is None

    channel = guild.created[0]
    assert channel.deleted
    assert await service.store.get(channel.id) is None


async def test_room_copies_category_overwrites_without_manage_roles(
    service, guild, trigger, category
) -> None:
    category.overwrites[guild.default_role].manage_roles = True

    _, _, channel = await open_room(service, guild, trigger)

    assert channel.overwrites[guild.default_role].manage_roles is None


async def test_room_is_still_created_when_overwrites_are_refused(service, guild, trigger) -> None:
    guild.reject_overwrites = True

    member, room, channel = await open_room(service, guild, trigger)

    assert room is not None
    assert member.voice.channel is channel


async def test_last_person_leaving_deletes_the_room(service, guild, trigger) -> None:
    member, _, channel = await open_room(service, guild, trigger)
    member.connect_to(None)

    assert await service.on_leave(member, channel) is None

    assert channel.deleted
    assert await service.store.get(channel.id) is None


async def test_room_with_only_a_bot_left_is_deleted(service, guild, trigger) -> None:
    member, _, channel = await open_room(service, guild, trigger)
    guild.add_member("MusicBot", bot=True).connect_to(channel)
    member.connect_to(None)

    await service.on_leave(member, channel)

    assert channel.deleted


async def test_owner_leaving_hands_the_room_to_someone_still_inside(
    service, guild, trigger
) -> None:
    owner, _, channel = await open_room(service, guild, trigger)
    friend = guild.add_member("Bob")
    friend.connect_to(channel)
    owner.connect_to(None)

    new_room = await service.on_leave(owner, channel)

    assert new_room is not None and new_room.owner_id == friend.id
    assert (await service.store.get(channel.id)).owner_id == friend.id
    assert not channel.deleted


async def test_guest_leaving_changes_nothing(service, guild, trigger) -> None:
    _, room, channel = await open_room(service, guild, trigger)
    guest = guild.add_member("Bob")
    guest.connect_to(channel)
    guest.connect_to(None)

    assert await service.on_leave(guest, channel) is None
    assert await service.store.get(channel.id) == room


async def test_leaving_a_channel_the_bot_did_not_create_never_deletes_it(service, guild) -> None:
    manual = guild.add_voice_channel("Bob's Palace")
    member = guild.add_member("Bob")

    assert await service.on_leave(member, manual) is None
    assert not manual.deleted


async def test_owner_can_transfer_to_someone_in_the_room(service, guild, trigger) -> None:
    owner, _, channel = await open_room(service, guild, trigger)
    friend = guild.add_member("Bob")
    friend.connect_to(channel)

    room = await service.transfer(owner, channel, friend)

    assert room.owner_id == friend.id
    with pytest.raises(UserFacingError, match="propriétaire"):
        await service.transfer(owner, channel, friend)


async def test_transfer_requires_target_in_the_room(service, guild, trigger) -> None:
    owner, _, channel = await open_room(service, guild, trigger)
    outsider = guild.add_member("Bob")

    with pytest.raises(UserFacingError, match="dans le salon"):
        await service.transfer(owner, channel, outsider)


async def test_transfer_to_someone_who_already_owns_a_room_is_refused(
    service, guild, trigger
) -> None:
    owner, _, channel = await open_room(service, guild, trigger)
    other_owner, _, _ = await open_room(service, guild, trigger, "Bob")
    other_owner.connect_to(channel)

    with pytest.raises(UserFacingError, match="déjà son propre salon"):
        await service.transfer(owner, channel, other_owner)


async def test_only_the_owner_can_use_controls(service, guild, trigger) -> None:
    _, _, channel = await open_room(service, guild, trigger)
    intruder = guild.add_member("Bob")

    with pytest.raises(UserFacingError, match="Seul le propriétaire"):
        await service.rename(intruder, channel, "hack")
    with pytest.raises(UserFacingError, match="Seul le propriétaire"):
        await service.close(intruder, channel)


async def test_lock_then_unlock_restores_category_access(service, guild, trigger) -> None:
    owner, _, channel = await open_room(service, guild, trigger)
    friend = guild.add_member("Bob")
    friend.connect_to(channel)

    locked = await service.lock(owner, channel)

    assert locked.is_locked
    assert channel.overwrites[guild.default_role].connect is False
    assert channel.overwrites[friend].connect is True

    unlocked = await service.unlock(owner, channel)

    assert not unlocked.is_locked
    assert channel.overwrites[guild.default_role].connect is True
    assert (await service.store.get(channel.id)).is_locked is False


async def test_invite_grants_access_to_a_locked_room(service, guild, trigger) -> None:
    owner, _, channel = await open_room(service, guild, trigger)
    await service.lock(owner, channel)
    guest = guild.add_member("Bob")

    await service.invite(owner, channel, guest)

    assert channel.overwrites[guest].connect is True
    assert channel.overwrites[guest].view_channel is True


async def test_rename_and_limit(service, guild, trigger) -> None:
    owner, _, channel = await open_room(service, guild, trigger)

    assert await service.rename(owner, channel, "  Soirée   Valo ") == "Soirée Valo"
    await service.set_limit(owner, channel, 5)

    assert channel.name == "Soirée Valo"
    assert channel.user_limit == 5


async def test_close_deletes_the_room(service, guild, trigger) -> None:
    owner, _, channel = await open_room(service, guild, trigger)

    await service.close(owner, channel)

    assert channel.deleted
    assert await service.store.get(channel.id) is None


async def test_reconcile_repairs_state_after_downtime(service, guild, trigger) -> None:
    store = service.store
    empty = guild.add_voice_channel("empty")
    orphan_owner_room = guild.add_voice_channel("orphan")
    survivor = guild.add_member("Carol")
    survivor.connect_to(orphan_owner_room)
    untracked_empty = guild.add_voice_channel("manual")
    waiting = guild.add_member("Dave")
    waiting.connect_to(trigger)

    for channel_id, owner_id in [(empty.id, 1), (orphan_owner_room.id, 2), (999_999, 3)]:
        await store.add(VoiceRoom(channel_id, guild.id, owner_id, trigger.id))

    report = await service.reconcile(guild)

    assert report.removed == 2
    assert empty.deleted
    assert await store.get(999_999) is None
    assert [room.owner_id for room in report.transferred] == [survivor.id]
    assert [room.owner_id for room in report.created] == [waiting.id]
    assert not untracked_empty.deleted


async def test_forget_removes_rooms_deleted_by_hand(service, guild, trigger) -> None:
    _, _, channel = await open_room(service, guild, trigger)

    await service.forget(channel.id)

    assert await service.store.get(channel.id) is None


def test_room_name_is_clipped_to_discord_limit() -> None:
    assert room_name("A" * 150) == "A" * 100


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_invalid_names_are_rejected(name: str) -> None:
    with pytest.raises(UserFacingError):
        validate_name(name)


@pytest.mark.parametrize("limit", [-1, 100])
def test_invalid_limits_are_rejected(limit: int) -> None:
    with pytest.raises(UserFacingError):
        validate_limit(limit)


def test_successor_candidates_skip_bots(guild: FakeGuild) -> None:
    human = guild.add_member("Bob")
    bot = guild.add_member("Bot", bot=True)

    assert successor_candidates([bot, human], random.Random(1)) == [human]


def test_locked_overwrites_deny_every_role_and_allow_members() -> None:
    allow = discord.PermissionOverwrite(connect=True, speak=True)

    result = locked_overwrites({"members": allow}, ["everyone", "members"], ["alice"])

    assert result["everyone"].connect is False
    assert result["members"].connect is False
    assert result["members"].speak is True
    assert result["alice"].connect is True
    assert allow.connect is True


def test_unlocked_overwrites_restore_category_values_and_drop_empty_ones() -> None:
    current = {
        "everyone": discord.PermissionOverwrite(connect=False),
        "muted": discord.PermissionOverwrite(connect=False),
        "alice": discord.PermissionOverwrite(connect=True),
    }
    category = {"muted": discord.PermissionOverwrite(connect=False)}

    result = unlocked_overwrites(current, ["everyone", "muted"], category)

    assert "everyone" not in result
    assert result["muted"].connect is False
    assert result["alice"].connect is True


def test_inherited_overwrites_do_not_mutate_the_category() -> None:
    original = discord.PermissionOverwrite(manage_roles=True, connect=True)

    copied = inherited_overwrites({"staff": original})

    assert copied["staff"].manage_roles is None
    assert copied["staff"].connect is True
    assert original.manage_roles is True
