from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands

from mingati import __version__
from mingati.bot import MingatiBot
from mingati.providers.ai import AIProvider
from mingati.providers.jokes import BlaguesApiProvider
from mingati.utils.permissions import staff_only

log = logging.getLogger(__name__)


def describe_providers(
    ai: AIProvider | None,
    jokes: BlaguesApiProvider | None,
    game_sources: Iterable[str],
    server_kinds: Iterable[str],
) -> str:
    """One line per external dependency, so staff see what is configured at a glance."""
    return "\n".join(
        [
            f"IA : {ai.name} · `{ai.model}`" if ai else "IA : désactivée",
            "Blagues : blagues-api.fr" if jokes else "Blagues : secours (IA / liste)",
            f"Jeux gratuits : {', '.join(game_sources) or 'aucun'}",
            f"Serveurs : {', '.join(server_kinds) or 'aucun'}",
        ]
    )


def format_uptime(delta: timedelta) -> str:
    """Compact French uptime such as '2 j 3 h 14 min'."""
    minutes = int(delta.total_seconds()) // 60
    days, minutes = divmod(minutes, 24 * 60)
    hours, minutes = divmod(minutes, 60)
    parts = [f"{days} j"] if days else []
    if days or hours:
        parts.append(f"{hours} h")
    parts.append(f"{minutes} min")
    return " ".join(parts)


class Core(commands.Cog):
    admin_group = app_commands.Group(
        name="bot", description="Infos techniques sur le bot", guild_only=True
    )

    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot

    @admin_group.command(name="status", description="État technique du bot (staff)")
    @staff_only()
    async def status(self, interaction: discord.Interaction) -> None:
        embed = discord.Embed(title="État de Mingati Bot", color=discord.Color.blurple())
        embed.add_field(name="Version", value=__version__)
        embed.add_field(name="Uptime", value=format_uptime(datetime.now(UTC) - self.bot.started_at))
        embed.add_field(name="Latence Discord", value=f"{self.bot.latency * 1000:.0f} ms")
        embed.add_field(name="SQLite", value=await self._database_status(), inline=False)
        embed.add_field(name="Jeux gratuits", value=await self._free_games_status(), inline=False)
        embed.add_field(
            name="Providers",
            value=describe_providers(
                self.bot.billy.ai,
                self.bot.billy.jokes,
                (provider.label for provider in self.bot.free_games.providers),
                (provider.label for provider in self.bot.game_servers.providers.values()),
            ),
            inline=False,
        )
        embed.add_field(name="Dernière erreur", value=self._last_error(), inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _database_status(self) -> str:
        try:
            version = await self.bot.database.schema_version()
        except Exception:
            log.exception("SQLite health check failed")
            return "En erreur"
        return f"OK (schéma v{version})"

    async def _free_games_status(self) -> str:
        last = await self.bot.free_games.last_success()
        if last is None:
            return "Jamais rafraîchi"
        return (
            f"Dernier refresh {discord.utils.format_dt(last, 'R')} · détail : `/freegames status`"
        )

    def _last_error(self) -> str:
        error = self.bot.last_error.last_error
        if error is None:
            return "Aucune"
        timestamp = discord.utils.format_dt(error.at, "R")
        return f"{timestamp} · `{error.logger}` · {error.message[:200]}"


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Core(bot))
