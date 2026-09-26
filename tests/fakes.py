import asyncio
import itertools
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import discord

_ids = itertools.count(1000)


def http_error(kind: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return kind(SimpleNamespace(status=status, reason="fake"), "fake error")


@dataclass(eq=False)
class FakeRole:
    name: str
    id: int = field(default_factory=lambda: next(_ids))


@dataclass(eq=False)
class FakeCategory:
    overwrites: dict[Any, discord.PermissionOverwrite] = field(default_factory=dict)
    id: int = field(default_factory=lambda: next(_ids))


@dataclass(eq=False)
class FakeMessage:
    id: int = field(default_factory=lambda: next(_ids))


@dataclass(eq=False)
class FakeVoiceChannel:
    guild: "FakeGuild"
    name: str
    category: FakeCategory | None = None
    overwrites: dict[Any, discord.PermissionOverwrite] = field(default_factory=dict)
    user_limit: int = 0
    bitrate: int = 64000
    members: list["FakeMember"] = field(default_factory=list)
    sent: list[dict[str, Any]] = field(default_factory=list)
    deleted: bool = False
    type: discord.ChannelType = discord.ChannelType.voice
    id: int = field(default_factory=lambda: next(_ids))

    async def edit(self, **changes: Any) -> None:
        for key, value in changes.items():
            setattr(self, key, value)

    async def delete(self, reason: str | None = None) -> None:
        if self.deleted:
            raise http_error(discord.NotFound, 404)
        self.deleted = True
        self.guild.channels.pop(self.id, None)

    async def send(self, *args: Any, **kwargs: Any) -> FakeMessage:
        self.sent.append(kwargs)
        return FakeMessage()


@dataclass(eq=False)
class FakeMember:
    guild: "FakeGuild"
    display_name: str
    bot: bool = False
    voice: SimpleNamespace | None = None
    fail_move: bool = False
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def mention(self) -> str:
        return f"<@{self.id}>"

    def connect_to(self, channel: FakeVoiceChannel | None) -> None:
        if self.voice and self.voice.channel:
            self.voice.channel.members.remove(self)
        self.voice = SimpleNamespace(channel=channel) if channel else None
        if channel:
            channel.members.append(self)

    async def move_to(self, channel: FakeVoiceChannel) -> None:
        await asyncio.sleep(0)
        if self.fail_move or self.voice is None:
            raise http_error(discord.HTTPException, 400)
        self.connect_to(channel)


@dataclass(eq=False)
class FakeGuild:
    bitrate_limit: float = 96000.0
    reject_overwrites: bool = False
    channels: dict[int, FakeVoiceChannel] = field(default_factory=dict)
    default_role: FakeRole = field(default_factory=lambda: FakeRole("@everyone"))
    created: list[FakeVoiceChannel] = field(default_factory=list)
    id: int = field(default_factory=lambda: next(_ids))

    def get_channel(self, channel_id: int) -> FakeVoiceChannel | None:
        return self.channels.get(channel_id)

    def get_member(self, member_id: int) -> None:
        return None

    def add_voice_channel(
        self, name: str, category: FakeCategory | None = None
    ) -> FakeVoiceChannel:
        channel = FakeVoiceChannel(guild=self, name=name, category=category)
        self.channels[channel.id] = channel
        return channel

    def add_member(self, name: str, *, bot: bool = False) -> FakeMember:
        return FakeMember(guild=self, display_name=name, bot=bot)

    async def create_voice_channel(
        self,
        name: str,
        *,
        category: FakeCategory | None,
        bitrate: int,
        user_limit: int = 0,
        overwrites: dict[Any, discord.PermissionOverwrite] | None = None,
    ) -> FakeVoiceChannel:
        await asyncio.sleep(0)
        if overwrites is not None and self.reject_overwrites:
            raise http_error(discord.Forbidden, 403)
        channel = self.add_voice_channel(name, category)
        channel.bitrate = bitrate
        channel.user_limit = user_limit
        channel.overwrites = dict(overwrites or {})
        self.created.append(channel)
        return channel
