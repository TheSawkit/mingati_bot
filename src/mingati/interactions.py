import logging
from typing import Any

import discord
from discord import app_commands

from mingati.errors import UserFacingError

log = logging.getLogger(__name__)

GENERIC_ERROR = (
    "Oups, quelque chose a planté de mon côté. Le staff peut voir le détail dans les logs."
)
MISSING_PERMISSIONS = "Il me manque des permissions Discord pour faire ça. Préviens le staff."


def describe_error(error: Exception) -> str | None:
    """User-facing message for an expected failure, None when it is a real bug."""
    original = getattr(error, "original", error)
    if isinstance(original, UserFacingError):
        return str(original)
    if isinstance(original, discord.Forbidden | app_commands.BotMissingPermissions):
        return MISSING_PERMISSIONS
    if isinstance(error, app_commands.MissingAnyRole | app_commands.MissingRole):
        return "Cette commande est réservée au staff."
    if isinstance(error, app_commands.CommandOnCooldown):
        return f"Doucement ! Réessaie dans {error.retry_after:.0f} s."
    if isinstance(error, app_commands.NoPrivateMessage):
        return "Cette commande ne marche que sur le serveur."
    return None


async def reply_ephemeral(interaction: discord.Interaction, content: str) -> None:
    """Answer an interaction privately whether or not it has already been responded to."""
    if interaction.response.is_done():
        await interaction.followup.send(content, ephemeral=True)
    else:
        await interaction.response.send_message(content, ephemeral=True)


async def report_error(interaction: discord.Interaction, error: Exception, source: str) -> None:
    """Log unexpected errors and always give the user an understandable answer."""
    message = describe_error(error)
    original = getattr(error, "original", error)
    if message is None:
        log.error("Unhandled error in %s", source, exc_info=error)
        message = GENERIC_ERROR
    elif isinstance(original, discord.Forbidden):
        log.warning("Missing Discord permission in %s: %s", source, original.text)
    try:
        await reply_ephemeral(interaction, message)
    except discord.HTTPException:
        log.warning("Could not deliver error message to the user", exc_info=True)


class MingatiView(discord.ui.View):
    """View whose callback errors are reported like slash command errors."""

    async def on_error(
        self, interaction: discord.Interaction, error: Exception, item: discord.ui.Item[Any]
    ) -> None:
        await report_error(interaction, error, type(self).__name__)


class MingatiModal(discord.ui.Modal):
    """Modal whose submit errors are reported like slash command errors."""

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await report_error(interaction, error, type(self).__name__)
