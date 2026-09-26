from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.services.guild_config import GuildConfigStore
from mingati.utils.permissions import staff_only
from mingati.views.hub import (
    ACTIVITIES,
    HubView,
    build_hub_embed,
    describe_free_games,
    describe_sessions,
    describe_voice_triggers,
)

log = logging.getLogger(__name__)

HUB_CHANNEL_KEY = "hub_channel_id"
HUB_MESSAGE_KEY = "hub_message_id"


class Hub(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.config = GuildConfigStore(bot.database)
        self.view = HubView(self)

    async def cog_load(self) -> None:
        self.bot.add_view(self.view)

    @app_commands.command(name="mingati", description="Publie ou met à jour le hub Mingati (staff)")
    @app_commands.guild_only()
    @staff_only()
    async def mingati(self, interaction: discord.Interaction) -> None:
        if not isinstance(interaction.channel, discord.TextChannel):
            raise UserFacingError("Lance cette commande dans un salon textuel.")
        guild_id = interaction.channel.guild.id
        await interaction.response.defer(ephemeral=True, thinking=True)
        existing = await self._existing_hub(guild_id)
        if existing and existing.channel.id == interaction.channel.id:
            await existing.edit(embed=build_hub_embed(), view=self.view)
            await interaction.followup.send("✅ Hub mis à jour.", ephemeral=True)
            return
        if existing:
            await existing.delete()
        message = await interaction.channel.send(embed=build_hub_embed(), view=self.view)
        await self.config.set(guild_id, HUB_CHANNEL_KEY, str(message.channel.id))
        await self.config.set(guild_id, HUB_MESSAGE_KEY, str(message.id))
        await interaction.followup.send(f"✅ Hub publié : {message.jump_url}", ephemeral=True)

    async def show_sessions(self, interaction: discord.Interaction) -> None:
        guild_id = interaction.guild_id or self.bot.settings.discord_guild_id
        sessions = await self.bot.gaming_sessions.list_open(guild_id, datetime.now(UTC))
        await interaction.response.send_message(
            describe_sessions(sessions, guild_id), ephemeral=True
        )

    async def show_voice(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            describe_voice_triggers(self.bot.settings.voice_trigger_ids), ephemeral=True
        )

    async def show_free_games(self, interaction: discord.Interaction) -> None:
        games = await self.bot.free_games.active(datetime.now(UTC))
        await interaction.response.send_message(describe_free_games(games), ephemeral=True)

    async def show_activities(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_message(ACTIVITIES, ephemeral=True)

    async def ask_billy(self, interaction: discord.Interaction, question: str) -> None:
        cleaned = self.bot.billy.prepare_question(interaction.user.id, question, datetime.now(UTC))
        if self.bot.http_session is None:
            raise UserFacingError("Je me réveille à peine, réessaie dans un instant...")
        await interaction.response.defer(ephemeral=True, thinking=True)
        reply = await self.bot.billy.answer(self.bot.http_session, cleaned)
        await interaction.followup.send(f"> {cleaned}\n{reply}", ephemeral=True)

    async def _existing_hub(self, guild_id: int) -> discord.Message | None:
        channel_id = await self.config.get(guild_id, HUB_CHANNEL_KEY)
        message_id = await self.config.get(guild_id, HUB_MESSAGE_KEY)
        channel = self.bot.get_channel(int(channel_id)) if channel_id else None
        if not isinstance(channel, discord.TextChannel) or message_id is None:
            return None
        try:
            return await channel.fetch_message(int(message_id))
        except discord.NotFound:
            return None


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Hub(bot))
