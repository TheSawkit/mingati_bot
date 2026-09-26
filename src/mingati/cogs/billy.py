from __future__ import annotations

import logging
import re
from datetime import UTC, datetime

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.services.billy import MAX_QUESTION_LENGTH

log = logging.getLogger(__name__)

JOKE_COOLDOWN_SECONDS = 10


def strip_bot_mention(content: str, bot_id: int) -> str:
    return re.sub(rf"<@!?{bot_id}>", "", content).strip()


class Billy(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.service = bot.billy

    async def cog_load(self) -> None:
        if self.bot.settings.billy_mentions_enabled:
            self.bot.add_listener(self.on_mention, "on_message")
        if self.bot.settings.welcome_enabled:
            self.bot.add_listener(self.welcome, "on_member_join")

    @app_commands.command(name="billy", description="Pose une question à Billy")
    @app_commands.guild_only()
    @app_commands.describe(question="Ta question pour Billy")
    async def billy(
        self,
        interaction: discord.Interaction,
        question: app_commands.Range[str, 1, MAX_QUESTION_LENGTH],
    ) -> None:
        cleaned = self.service.prepare_question(interaction.user.id, question, datetime.now(UTC))
        await interaction.response.defer(thinking=True)
        reply = await self.service.answer(self._http(), cleaned)
        await interaction.followup.send(
            f"> {cleaned}\n{reply}", allowed_mentions=discord.AllowedMentions.none()
        )

    @app_commands.command(name="blague", description="Billy raconte une blague")
    @app_commands.guild_only()
    @app_commands.checks.cooldown(1, JOKE_COOLDOWN_SECONDS, key=lambda i: i.user.id)
    async def blague(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer(thinking=True)
        joke = await self.service.joke(self._http())
        await interaction.followup.send(f"{joke.setup}\n||{joke.punchline}||")

    async def on_mention(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or self.bot.user is None:
            return
        if self.bot.user not in message.mentions:
            return
        text = strip_bot_mention(message.content, self.bot.user.id)
        if not text:
            return
        try:
            question = self.service.prepare_question(message.author.id, text, datetime.now(UTC))
        except UserFacingError as error:
            await message.reply(str(error), mention_author=False)
            return
        async with message.channel.typing():
            reply = await self.service.answer(self._http(), question)
        await message.reply(
            reply, mention_author=False, allowed_mentions=discord.AllowedMentions.none()
        )

    async def welcome(self, member: discord.Member) -> None:
        if member.bot or member.guild.id != self.bot.settings.discord_guild_id:
            return
        channel = self.bot.get_channel(self.bot.settings.channel_chat_id or 0)
        if not isinstance(channel, discord.TextChannel):
            log.warning("CHANNEL_CHAT_ID not found, welcome message skipped")
            return
        text = await self.service.welcome(self._http(), member.mention, member.display_name)
        await channel.send(text, allowed_mentions=discord.AllowedMentions(users=[member]))

    def _http(self) -> aiohttp.ClientSession:
        if self.bot.http_session is None:
            raise UserFacingError("Je me réveille à peine, réessaie dans un instant...")
        return self.bot.http_session


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Billy(bot))
