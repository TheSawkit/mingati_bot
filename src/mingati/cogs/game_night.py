from __future__ import annotations

from datetime import datetime

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.services.game_night import MAX_DESCRIPTION_LENGTH, plan_game_night
from mingati.services.gaming_sessions import MAX_PLAYERS, MIN_PLAYERS

EVENT_LOCATION = "Discord Mingati"


class GameNight(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="game-night", description="Programme une soirée jeu (événement Discord)"
    )
    @app_commands.guild_only()
    @app_commands.describe(
        jeu="Le jeu",
        date="aujourd'hui, demain, 27/09 ou 27/09/2026",
        heure="21h, 21h30 ou 21:30",
        joueurs=f"Nombre de joueurs ({MIN_PLAYERS} à {MAX_PLAYERS})",
        description="Détails (optionnel)",
    )
    async def game_night(
        self,
        interaction: discord.Interaction,
        jeu: app_commands.Range[str, 1, 80],
        date: app_commands.Range[str, 1, 20],
        heure: app_commands.Range[str, 1, 10],
        joueurs: app_commands.Range[int, MIN_PLAYERS, MAX_PLAYERS],
        description: app_commands.Range[str, 1, MAX_DESCRIPTION_LENGTH] | None = None,
    ) -> None:
        if interaction.guild is None:
            raise UserFacingError("Cette commande ne marche que sur le serveur.")
        night = plan_game_night(
            game=jeu,
            day=date,
            time=heure,
            players=joueurs,
            description=description,
            host_name=interaction.user.display_name,
            now=datetime.now(self.bot.settings.timezone),
        )
        await interaction.response.defer(thinking=True)
        event = await interaction.guild.create_scheduled_event(
            name=night.event_name,
            start_time=night.starts_at,
            end_time=night.ends_at,
            entity_type=discord.EntityType.external,
            privacy_level=discord.PrivacyLevel.guild_only,
            location=EVENT_LOCATION,
            description=night.event_description,
            reason=f"/game-night par {interaction.user.id}",
        )
        await interaction.followup.send(
            f"🎮 **GAME NIGHT** — **{night.game}**, "
            f"{discord.utils.format_dt(night.starts_at, 'F')} "
            f"({discord.utils.format_dt(night.starts_at, 'R')}) · 👥 {night.players} joueurs\n"
            f"Clique sur « Intéressé » pour être prévenu : {event.url}",
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(GameNight(bot))
