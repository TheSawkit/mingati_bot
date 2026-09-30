from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.views.media import send_watch_search


class Media(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot

    @app_commands.command(
        name="watch",
        description="Chercher un film ou une série et voir où le regarder",
    )
    @app_commands.guild_only()
    async def watch(
        self,
        interaction: discord.Interaction,
        film: app_commands.Range[str, 2, 100],
    ) -> None:
        if self.bot.http_session is None:
            raise UserFacingError("Le bot n'est pas encore prêt, réessaie dans un instant.")
        await send_watch_search(
            interaction,
            self.bot.media,
            self.bot.http_session,
            interaction.user.id,
            film,
        )


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Media(bot))
