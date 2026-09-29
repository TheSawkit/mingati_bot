from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.views.media import WatchModal


class Media(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="watch",
        description="Chercher un film ou une série et voir où le regarder",
    )
    @app_commands.guild_only()
    async def watch(self, interaction: discord.Interaction) -> None:
        if self.bot.http_session is None:
            raise UserFacingError("Le bot n'est pas encore prêt, réessaie dans un instant.")
        await interaction.response.send_modal(
            WatchModal(
                self.bot.media,
                self.bot.http_session,
                interaction.user.id,
            )
        )


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Media(bot))
