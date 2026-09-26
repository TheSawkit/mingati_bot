from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.services.game_servers import MAX_NAME_LENGTH
from mingati.utils.permissions import staff_only
from mingati.views.servers import build_servers_embed

MAX_AUTOCOMPLETE = 25


class Servers(commands.Cog):
    server = app_commands.Group(
        name="server", description="Serveurs de jeux de Mingati", guild_only=True
    )

    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.service = bot.game_servers
        self.kind_choices = [
            app_commands.Choice(name=provider.label, value=kind)
            for kind, provider in self.service.providers.items()
        ]

    async def server_names(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        servers = await self.service.list_servers(interaction.guild_id or 0)
        return [
            app_commands.Choice(name=server.name, value=server.name)
            for server in servers
            if current.casefold() in server.name.casefold()
        ][:MAX_AUTOCOMPLETE]

    @server.command(name="status", description="État des serveurs de jeux")
    @app_commands.describe(nom="Un serveur précis (tous par défaut)")
    async def status(self, interaction: discord.Interaction, nom: str | None = None) -> None:
        await interaction.response.defer(thinking=True)
        results = await self.service.statuses(interaction.guild_id or 0, nom)
        await interaction.followup.send(embed=build_servers_embed(results))

    @server.command(name="add", description="Ajoute un serveur à suivre (staff)")
    @app_commands.describe(nom="Nom affiché", adresse="host ou host:port", type="Jeu")
    @staff_only()
    async def add(
        self,
        interaction: discord.Interaction,
        nom: app_commands.Range[str, 1, MAX_NAME_LENGTH],
        adresse: app_commands.Range[str, 1, 260],
        type: str = "minecraft",
    ) -> None:
        server = await self.service.add(interaction.guild_id or 0, nom, type, adresse)
        await interaction.response.send_message(
            f"✅ Serveur **{server.name}** (`{server.address}`) ajouté.", ephemeral=True
        )

    @server.command(name="remove", description="Retire un serveur suivi (staff)")
    @app_commands.describe(nom="Le serveur à retirer")
    @staff_only()
    async def remove(self, interaction: discord.Interaction, nom: str) -> None:
        await self.service.remove(interaction.guild_id or 0, nom)
        await interaction.response.send_message(f"🗑️ Serveur **{nom}** retiré.", ephemeral=True)

    @status.autocomplete("nom")
    async def status_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.server_names(interaction, current)

    @remove.autocomplete("nom")
    async def remove_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return await self.server_names(interaction, current)

    @add.autocomplete("type")
    async def kind_autocomplete(
        self, interaction: discord.Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        return self.kind_choices


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Servers(bot))
