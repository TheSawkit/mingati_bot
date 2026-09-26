from __future__ import annotations

import logging
from datetime import UTC, datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.services.gaming_sessions import (
    DEFAULT_DURATION_HOURS,
    MAX_DURATION_HOURS,
    MAX_PLAYERS,
    MIN_PLAYERS,
    GamingSession,
    plan_session,
)
from mingati.services.session_voice import SessionVoice, open_session_voice
from mingati.views.gaming import PLATFORMS, SessionView, build_session_embed

log = logging.getLogger(__name__)

CardChannel = discord.TextChannel | discord.VoiceChannel | discord.Thread

PLATFORM_CHOICES = [app_commands.Choice(name=name, value=name) for name in PLATFORMS]


class Gaming(commands.Cog):
    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.sessions = bot.gaming_sessions
        self.view = SessionView(self)

    async def cog_load(self) -> None:
        self.bot.add_view(self.view)
        self.expire_sessions.start()

    async def cog_unload(self) -> None:
        self.expire_sessions.cancel()

    @app_commands.command(name="jouer", description="Cherche des joueurs pour une partie")
    @app_commands.guild_only()
    @app_commands.describe(
        jeu="Le jeu",
        plateforme="Sur quoi on joue",
        joueurs=f"Nombre total de joueurs ({MIN_PLAYERS} à {MAX_PLAYERS})",
        mode="Mode de jeu (optionnel) : ranked, coop, fun…",
        heure="Début (optionnel) : 21h, 21h30, maintenant",
        duree=f"Durée en heures avant expiration (défaut {DEFAULT_DURATION_HOURS})",
    )
    @app_commands.choices(plateforme=PLATFORM_CHOICES)
    async def jouer(
        self,
        interaction: discord.Interaction,
        jeu: app_commands.Range[str, 1, 80],
        plateforme: app_commands.Choice[str],
        joueurs: app_commands.Range[int, MIN_PLAYERS, MAX_PLAYERS],
        mode: app_commands.Range[str, 1, 50] | None = None,
        heure: app_commands.Range[str, 1, 10] | None = None,
        duree: app_commands.Range[int, 1, MAX_DURATION_HOURS] = DEFAULT_DURATION_HOURS,
    ) -> None:
        channel = self._cards_channel(interaction)
        now = datetime.now(self.bot.settings.tz)
        planned = plan_session(
            guild_id=interaction.guild_id or 0,
            channel_id=channel.id,
            host_id=interaction.user.id,
            game=jeu,
            platform=plateforme.value,
            mode=mode,
            max_players=joueurs,
            start=heure,
            duration_hours=duree,
            now=now,
        )
        session = await self.sessions.create(planned, now)
        try:
            message = await channel.send(
                content=f"🎯 **{interaction.user.display_name}** cherche des joueurs !",
                embed=build_session_embed(session),
                view=self.view,
            )
        except discord.HTTPException:
            await self.sessions.delete(session.id)
            raise
        await self.sessions.attach_message(session.id, message.id)
        await interaction.response.send_message(
            f"✅ Session publiée : {message.jump_url}", ephemeral=True
        )

    async def join(self, interaction: discord.Interaction) -> None:
        session = await self._session_of(interaction)
        updated = await self.sessions.join(session.id, interaction.user.id)
        await interaction.response.edit_message(embed=build_session_embed(updated), view=self.view)

    async def leave(self, interaction: discord.Interaction) -> None:
        session = await self._session_of(interaction)
        updated = await self.sessions.leave(session.id, interaction.user.id)
        if updated is not None:
            await interaction.response.edit_message(
                embed=build_session_embed(updated), view=self.view
            )
            return
        await interaction.response.send_message(
            "Plus personne dans la session, je la retire.", ephemeral=True
        )
        await self._delete_card(session)

    async def open_voice(self, interaction: discord.Interaction) -> None:
        session = await self._session_of(interaction)
        if not isinstance(interaction.user, discord.Member):
            raise UserFacingError("Cette commande ne marche que sur le serveur.")
        trigger = self.bot.get_channel(self.bot.settings.channel_create_voice_gaming_id or 0)
        await interaction.response.defer(ephemeral=True, thinking=True)
        result = await open_session_voice(
            self.sessions,
            self.bot.voice_rooms,
            session,
            interaction.user,
            trigger if isinstance(trigger, discord.VoiceChannel) else None,
        )
        if result.already_open:
            await interaction.followup.send(
                f"🎙 Le vocal existe déjà : <#{result.channel_id}>", ephemeral=True
            )
            return
        if result.created_room:
            self.bot.dispatch("voice_room_created", result.created_room)
        await self._edit_card(result.session)
        await interaction.followup.send(f"🎙 Vocal prêt : <#{result.channel_id}>", ephemeral=True)
        await self._announce_voice(result)

    async def _announce_voice(self, result: SessionVoice) -> None:
        card = self._card(result.session)
        if not result.guests or card is None:
            return
        mentions = " ".join(f"<@{guest.id}>" for guest in result.guests)
        await card.reply(
            f"🎙 Vocal prêt pour **{result.session.game}** : <#{result.channel_id}> {mentions}",
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @tasks.loop(minutes=1)
    async def expire_sessions(self) -> None:
        for session in await self.sessions.pop_expired(datetime.now(UTC)):
            await self._delete_card(session)
            log.info("Gaming session %s expired", session.id)

    @expire_sessions.before_loop
    async def before_expire(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        for session in await self.sessions.detach_voice_channel(channel.id):
            await self._edit_card(session)

    @commands.Cog.listener()
    async def on_raw_member_remove(self, payload: discord.RawMemberRemoveEvent) -> None:
        changes = await self.sessions.remove_member_everywhere(payload.guild_id, payload.user.id)
        for before, after in changes:
            if after is None:
                await self._delete_card(before)
            else:
                await self._edit_card(after)

    def _cards_channel(self, interaction: discord.Interaction) -> CardChannel:
        configured = self.bot.get_channel(self.bot.settings.channel_who_plays_id or 0)
        channel = configured or interaction.channel
        if not isinstance(channel, CardChannel):
            raise UserFacingError("Je ne trouve pas de salon où publier la session.")
        return channel

    async def _session_of(self, interaction: discord.Interaction) -> GamingSession:
        if interaction.message is None:
            raise UserFacingError("Cette session n'existe plus.")
        return await self.sessions.get_by_message(interaction.message.id)

    async def _edit_card(self, session: GamingSession) -> None:
        message = self._card(session)
        if message is None:
            return
        try:
            await message.edit(embed=build_session_embed(session), view=self.view)
        except discord.NotFound:
            await self.sessions.delete(session.id)

    async def _delete_card(self, session: GamingSession) -> None:
        message = self._card(session)
        if message is None:
            return
        try:
            await message.delete()
        except discord.NotFound:
            log.debug("Card of session %s was already deleted", session.id)

    def _card(self, session: GamingSession) -> discord.PartialMessage | None:
        channel = self.bot.get_channel(session.channel_id)
        if session.message_id is None or not isinstance(channel, CardChannel):
            return None
        return channel.get_partial_message(session.message_id)


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Gaming(bot))
