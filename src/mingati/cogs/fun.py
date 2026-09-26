from __future__ import annotations

import random
from collections.abc import Callable

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.services.fun import (
    MAX_DICE,
    MAX_FACES,
    flip_coin,
    pick_game,
    pull_trigger,
    roll_dice,
    shake_eight_ball,
)

FUN_COOLDOWN_SECONDS = 3


def fun_cooldown[T]() -> Callable[[T], T]:
    return app_commands.checks.cooldown(1, FUN_COOLDOWN_SECONDS, key=lambda i: i.user.id)


class Fun(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.rng = random.SystemRandom()

    @app_commands.command(name="dé", description="Lance un ou plusieurs dés")
    @app_commands.guild_only()
    @app_commands.describe(faces="Nombre de faces (6 par défaut)", nombre="Nombre de dés")
    @fun_cooldown()
    async def dice(
        self,
        interaction: discord.Interaction,
        faces: app_commands.Range[int, 2, MAX_FACES] = 6,
        nombre: app_commands.Range[int, 1, MAX_DICE] = 1,
    ) -> None:
        rolls = roll_dice(faces, nombre, self.rng)
        total = f" = **{sum(rolls)}**" if len(rolls) > 1 else ""
        await interaction.response.send_message(
            f"🎲 {' + '.join(map(str, rolls))}{total} (d{faces})"
        )

    @app_commands.command(name="coinflip", description="Pile ou face")
    @app_commands.guild_only()
    @fun_cooldown()
    async def coinflip(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(f"🪙 **{flip_coin(self.rng)}** !")

    @app_commands.command(name="8ball", description="Pose une question à la boule magique")
    @app_commands.guild_only()
    @app_commands.describe(question="Ta question (oui/non)")
    @fun_cooldown()
    async def eight_ball(
        self, interaction: discord.Interaction, question: app_commands.Range[str, 1, 200]
    ) -> None:
        await interaction.response.send_message(
            f"> {question}\n🎱 {shake_eight_ball(self.rng)}",
            allowed_mentions=discord.AllowedMentions.none(),
        )

    @app_commands.command(name="roulette", description="Roulette russe (1 chance sur 6)")
    @app_commands.guild_only()
    @app_commands.describe(membre="Qui tente sa chance (toi par défaut)")
    @fun_cooldown()
    async def roulette(
        self, interaction: discord.Interaction, membre: discord.Member | None = None
    ) -> None:
        target = membre or interaction.user
        outcome = (
            "💥 **PAN !** Pas de chance..." if pull_trigger(self.rng) else "*clic*... ouf 😮‍💨"
        )
        await interaction.response.send_message(
            f"🔫 {target.mention} appuie sur la détente... {outcome}",
            allowed_mentions=discord.AllowedMentions(users=[target]),
        )

    @app_commands.command(name="random-game", description="Tire au sort le jeu de ce soir")
    @app_commands.guild_only()
    @app_commands.describe(choix="Les jeux, séparés par des virgules")
    @fun_cooldown()
    async def random_game(
        self, interaction: discord.Interaction, choix: app_commands.Range[str, 3, 500]
    ) -> None:
        await interaction.response.send_message(
            f"🎯 Ce soir on joue à... **{pick_game(choix, self.rng)}** !",
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Fun(bot))
