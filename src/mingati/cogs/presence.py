from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.services.presence import describe_playing


class Presence(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot

    @app_commands.command(name="en-jeu", description="Qui joue à quoi en ce moment ?")
    @app_commands.guild_only()
    async def playing_now(self, interaction: discord.Interaction) -> None:
        members = interaction.guild.members if interaction.guild else []
        await interaction.response.send_message(
            describe_playing(members), allowed_mentions=discord.AllowedMentions.none()
        )


async def setup(bot: MingatiBot) -> None:
    if bot.settings.presence_enabled:
        await bot.add_cog(Presence(bot))
