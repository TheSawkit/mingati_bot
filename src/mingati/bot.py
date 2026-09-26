import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from mingati.config import Settings
from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.utils.logging import LastErrorHandler

log = logging.getLogger(__name__)

EXTENSIONS = ("mingati.cogs.core",)

GENERIC_ERROR = (
    "Oups, quelque chose a planté de mon côté. Le staff peut voir le détail dans les logs."
)


def build_intents() -> discord.Intents:
    """Least-privilege gateway intents; features opt in to extra intents explicitly."""
    return discord.Intents(guilds=True)


def describe_error(error: app_commands.AppCommandError) -> str | None:
    """User-facing message for an expected app command failure, None when it is a real bug."""
    original = getattr(error, "original", error)
    if isinstance(original, UserFacingError):
        return str(original)
    if isinstance(error, app_commands.MissingAnyRole | app_commands.MissingRole):
        return "Cette commande est réservée au staff."
    if isinstance(error, app_commands.CommandOnCooldown):
        return f"Doucement ! Réessaie dans {error.retry_after:.0f} s."
    if isinstance(error, app_commands.NoPrivateMessage):
        return "Cette commande ne marche que sur le serveur."
    if isinstance(error, app_commands.BotMissingPermissions):
        return "Il me manque des permissions Discord pour faire ça. Préviens le staff."
    return None


async def reply_ephemeral(interaction: discord.Interaction, content: str) -> None:
    """Answer an interaction privately whether or not it has already been responded to."""
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


class MingatiTree(app_commands.CommandTree):
    async def on_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        message = describe_error(error)
        if message is None:
            command = interaction.command.qualified_name if interaction.command else "?"
            log.error("Unhandled error in /%s", command, exc_info=error)
            message = GENERIC_ERROR
        try:
            await reply_ephemeral(interaction, message)
        except discord.HTTPException:
            log.warning("Could not deliver error message to the user", exc_info=True)


class MingatiBot(commands.Bot):
    """Bootstrap only: wires settings, database and cogs, then syncs slash commands to the guild."""

    def __init__(
        self, settings: Settings, database: Database, last_error: LastErrorHandler
    ) -> None:
        super().__init__(
            command_prefix=commands.when_mentioned,
            intents=build_intents(),
            help_command=None,
            tree_cls=MingatiTree,
            allowed_mentions=discord.AllowedMentions(everyone=False, roles=False),
        )
        self.settings = settings
        self.database = database
        self.last_error = last_error
        self.started_at = datetime.now(UTC)

    @property
    def guild_object(self) -> discord.Object:
        return discord.Object(id=self.settings.discord_guild_id)

    async def setup_hook(self) -> None:
        for extension in EXTENSIONS:
            await self.load_extension(extension)
        self.tree.copy_global_to(guild=self.guild_object)
        synced = await self.tree.sync(guild=self.guild_object)
        log.info("Synced %d slash commands to guild %s", len(synced), self.guild_object.id)

    async def on_ready(self) -> None:
        log.info("Connected as %s", self.user)
        if self.get_guild(self.settings.discord_guild_id) is None:
            log.error("Bot is not a member of guild %s", self.settings.discord_guild_id)
