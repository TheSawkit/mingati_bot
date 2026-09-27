from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.providers.games import FreeGame
from mingati.services.free_games import RefreshReport
from mingati.utils.permissions import staff_only
from mingati.views.free_games import (
    build_announcement,
    build_status_embed,
    find_logo,
    platform_style,
)

log = logging.getLogger(__name__)

REFRESH_INTERVAL_HOURS = 2


def describe_report(report: RefreshReport) -> str:
    """One-line-per-source summary of a manual refresh, for staff."""
    lines = [f"✅ {label} : {count} jeu(x)" for label, count in report.found.items()]
    lines += [f"⚠️ {label} : {error[:150]}" for label, error in report.errors.items()]
    lines.append(f"📣 {report.published} nouvelle(s) annonce(s)")
    return "\n".join(lines)


class FreeGames(commands.Cog):
    freegames = app_commands.Group(
        name="freegames", description="Jeux gratuits Steam, Epic et GOG", guild_only=True
    )

    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.service = bot.free_games

    async def cog_load(self) -> None:
        if self.bot.settings.channel_free_games_id is None:
            log.warning("CHANNEL_FREE_GAMES_ID not configured, free games are disabled")
            return
        self.refresh_loop.start()

    async def cog_unload(self) -> None:
        self.refresh_loop.cancel()

    @tasks.loop(hours=REFRESH_INTERVAL_HOURS)
    async def refresh_loop(self) -> None:
        try:
            report = await self._refresh()
        except UserFacingError as error:
            log.warning("Free games refresh skipped: %s", error)
            return
        log.info("Free games refreshed: %s", describe_report(report).replace("\n", " | "))

    @refresh_loop.before_loop
    async def before_refresh(self) -> None:
        await self.bot.wait_until_ready()

    @freegames.command(name="refresh", description="Vérifie les jeux gratuits maintenant (staff)")
    @staff_only()
    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(ephemeral=True, thinking=True)
        report = await self._refresh()
        await interaction.followup.send(describe_report(report), ephemeral=True)

    @freegames.command(name="status", description="État des sources de jeux gratuits (staff)")
    @staff_only()
    async def status(self, interaction: discord.Interaction) -> None:
        embed = build_status_embed(
            await self.service.statuses(), await self.service.active(datetime.now(UTC))
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _refresh(self) -> RefreshReport:
        channel = self.bot.get_channel(self.bot.settings.channel_free_games_id or 0)
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            raise UserFacingError(
                "Le salon des jeux gratuits est introuvable (CHANNEL_FREE_GAMES_ID)."
            )
        if self.bot.http_session is None:
            raise UserFacingError("Le bot n'est pas encore prêt, réessaie dans un instant.")

        async def publish(game: FreeGame) -> int:
            logo = find_logo(channel.guild.emojis, platform_style(game.source))
            announcement = build_announcement(game, logo)
            message = await channel.send(
                content=announcement.content, embed=announcement.embed, view=announcement.view
            )
            return message.id

        return await self.service.refresh(self.bot.http_session, publish, datetime.now(UTC))


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(FreeGames(bot))
