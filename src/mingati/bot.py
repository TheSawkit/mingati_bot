import logging
from datetime import UTC, datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from mingati.config import Settings
from mingati.database import Database
from mingati.interactions import report_error
from mingati.providers.ai import create_ai_provider
from mingati.providers.games import default_game_providers
from mingati.providers.http import create_http_session
from mingati.providers.jokes import create_joke_provider
from mingati.providers.servers import default_server_providers
from mingati.services.billy import BillyService
from mingati.services.free_games import FreeGameService
from mingati.services.game_servers import GameServerService
from mingati.services.gaming_sessions import GamingSessionService
from mingati.services.voice_rooms import VoiceRoomService, VoiceRoomStore
from mingati.utils.logging import LastErrorHandler

log = logging.getLogger(__name__)

EXTENSIONS = (
    "mingati.cogs.core",
    "mingati.cogs.voice",
    "mingati.cogs.gaming",
    "mingati.cogs.free_games",
    "mingati.cogs.billy",
    "mingati.cogs.hub",
    "mingati.cogs.fun",
    "mingati.cogs.game_night",
    "mingati.cogs.servers",
)


def build_intents(settings: Settings) -> discord.Intents:
    """Least-privilege gateway intents; optional features opt in explicitly."""
    return discord.Intents(
        guilds=True,
        voice_states=True,
        guild_messages=settings.billy_mentions_enabled,
        members=settings.welcome_enabled,
    )


class MingatiTree(app_commands.CommandTree):
    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        command = interaction.command.qualified_name if interaction.command else "?"
        await report_error(interaction, error, f"/{command}")


class MingatiBot(commands.Bot):
    """Bootstrap only: wires settings, database and cogs, then syncs slash commands to the guild."""

    def __init__(
        self, settings: Settings, database: Database, last_error: LastErrorHandler
    ) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=build_intents(settings),
            help_command=None,
            tree_cls=MingatiTree,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )
        self.settings = settings
        self.database = database
        self.last_error = last_error
        self.voice_rooms = VoiceRoomService(VoiceRoomStore(database), settings.voice_trigger_ids)
        self.gaming_sessions = GamingSessionService(database)
        self.free_games = FreeGameService(database, default_game_providers(settings.store_country))
        self.billy = BillyService(create_ai_provider(settings), create_joke_provider(settings))
        self.game_servers = GameServerService(database, default_server_providers())
        self.http_session: aiohttp.ClientSession | None = None
        self.started_at = datetime.now(UTC)

    @property
    def guild_object(self) -> discord.Object:
        return discord.Object(id=self.settings.discord_guild_id)

    async def setup_hook(self) -> None:
        self.http_session = create_http_session()
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        self.tree.copy_global_to(guild=self.guild_object)
        synced = await self.tree.sync(guild=self.guild_object)
        log.info("Synced %d slash commands to guild %s", len(synced), self.guild_object.id)

    async def close(self) -> None:
        if self.http_session is not None:
            await self.http_session.close()
        await super().close()

    async def on_ready(self) -> None:
        log.info("Connected as %s", self.user)
        if self.get_guild(self.settings.discord_guild_id) is None:
            log.error("Bot is not a member of guild %s", self.settings.discord_guild_id)
