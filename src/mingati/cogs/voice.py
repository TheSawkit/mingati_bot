from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import discord
from discord import app_commands
from discord.ext import commands, tasks

from mingati.bot import MingatiBot
from mingati.errors import UserFacingError
from mingati.services.voice_rooms import VoiceRoom, humans
from mingati.views.voice import VoiceControlView, build_panel_embed

log = logging.getLogger(__name__)

UNUSED_ROOM_GRACE = timedelta(minutes=10)

RoomAction = Callable[[discord.Member, discord.VoiceChannel], Awaitable[str]]


class Voice(commands.Cog):
    vocal = app_commands.Group(
        name="vocal", description="Gère ton salon vocal temporaire", guild_only=True
    )

    def __init__(self, bot: MingatiBot) -> None:
        self.bot = bot
        self.service = bot.voice_rooms
        self.panel = VoiceControlView(self)

    async def cog_load(self) -> None:
        self.bot.add_view(self.panel)
        self.sweep_unused_rooms.start()
        if not self.service.trigger_ids:
            log.warning("No CHANNEL_CREATE_VOICE_*_ID configured, temporary rooms are disabled")

    async def cog_unload(self) -> None:
        self.sweep_unused_rooms.cancel()

    @tasks.loop(minutes=5)
    async def sweep_unused_rooms(self) -> None:
        guild = self.bot.get_guild(self.bot.settings.discord_guild_id)
        if guild is None:
            return
        cutoff = datetime.now(UTC) - UNUSED_ROOM_GRACE
        removed = await self.service.sweep_unused(guild, cutoff)
        if removed:
            log.info("Swept %d unused voice rooms", removed)

    @sweep_unused_rooms.before_loop
    async def before_sweep(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_voice_room_created(self, room: VoiceRoom) -> None:
        await self.post_panel(room)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        guild = self.bot.get_guild(self.bot.settings.discord_guild_id)
        if guild is None:
            return
        report = await self.service.reconcile(guild)
        for room in report.created:
            await self.post_panel(room)
        for room in report.transferred:
            await self.refresh_panel(room)
        log.info(
            "Voice rooms reconciled: %d removed, %d transferred, %d created",
            report.removed,
            len(report.transferred),
            len(report.created),
        )

    @commands.Cog.listener()
    async def on_voice_state_update(
        self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState
    ) -> None:
        if member.guild.id != self.bot.settings.discord_guild_id or before.channel == after.channel:
            return
        if isinstance(before.channel, discord.VoiceChannel):
            new_owner_room = await self.service.on_leave(member, before.channel)
            if new_owner_room:
                await self.refresh_panel(new_owner_room)
        if isinstance(after.channel, discord.VoiceChannel) and self.service.is_trigger(
            after.channel.id
        ):
            created = await self.service.on_trigger_join(member, after.channel)
            if created:
                await self.post_panel(created)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel) -> None:
        if isinstance(channel, discord.VoiceChannel):
            await self.service.forget(channel.id)

    async def post_panel(self, room: VoiceRoom) -> None:
        channel = self.bot.get_channel(room.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return
        try:
            message = await channel.send(
                content=f"<@{room.owner_id}>", embed=build_panel_embed(room), view=self.panel
            )
        except discord.HTTPException:
            log.warning("Could not post control panel in room %s", room.channel_id, exc_info=True)
            return
        await self.service.store.set_panel_message(room.channel_id, message.id)

    async def refresh_panel(self, room: VoiceRoom) -> None:
        channel = self.bot.get_channel(room.channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            return
        if room.panel_message_id is None:
            await self.post_panel(room)
            return
        try:
            await channel.get_partial_message(room.panel_message_id).edit(
                embed=build_panel_embed(room)
            )
        except discord.NotFound:
            await self.post_panel(room)

    def _context(
        self, interaction: discord.Interaction
    ) -> tuple[discord.Member, discord.VoiceChannel]:
        actor = interaction.user
        if not isinstance(actor, discord.Member):
            raise UserFacingError("Cette commande ne marche que sur le serveur.")
        if isinstance(interaction.channel, discord.VoiceChannel):
            return actor, interaction.channel
        if actor.voice and isinstance(actor.voice.channel, discord.VoiceChannel):
            return actor, actor.voice.channel
        raise UserFacingError("Rejoins d'abord ton salon vocal.")

    async def ensure_owner(self, interaction: discord.Interaction) -> None:
        actor, channel = self._context(interaction)
        await self.service.require_owned_room(actor, channel.id)

    def transfer_candidates(self, interaction: discord.Interaction) -> list[discord.Member]:
        actor, channel = self._context(interaction)
        return [member for member in humans(channel.members) if member.id != actor.id]

    async def _run(self, interaction: discord.Interaction, action: RoomAction) -> None:
        actor, channel = self._context(interaction)
        await interaction.response.defer(ephemeral=True, thinking=True)
        await interaction.followup.send(await action(actor, channel), ephemeral=True)

    async def rename(self, interaction: discord.Interaction, name: str) -> None:
        async def action(actor: discord.Member, channel: discord.VoiceChannel) -> str:
            new_name = await self.service.rename(actor, channel, name)
            return f"✏️ Salon renommé en **{new_name}**."

        await self._run(interaction, action)

    async def set_limit(self, interaction: discord.Interaction, limit: int) -> None:
        async def action(actor: discord.Member, channel: discord.VoiceChannel) -> str:
            await self.service.set_limit(actor, channel, limit)
            text = "Plus de limite de places." if limit == 0 else f"Limite fixée à {limit} places."
            return f"🔢 {text}"

        await self._run(interaction, action)

    async def lock(self, interaction: discord.Interaction) -> None:
        async def action(actor: discord.Member, channel: discord.VoiceChannel) -> str:
            await self.refresh_panel(await self.service.lock(actor, channel))
            return "🔒 Salon verrouillé : seuls les présents et les invités peuvent entrer."

        await self._run(interaction, action)

    async def unlock(self, interaction: discord.Interaction) -> None:
        async def action(actor: discord.Member, channel: discord.VoiceChannel) -> str:
            await self.refresh_panel(await self.service.unlock(actor, channel))
            return "🔓 Salon ouvert à tout le monde."

        await self._run(interaction, action)

    async def invite(self, interaction: discord.Interaction, guest: discord.Member) -> None:
        async def action(actor: discord.Member, channel: discord.VoiceChannel) -> str:
            await self.service.invite(actor, channel, guest)
            await channel.send(
                f"{guest.mention}, {actor.display_name} t'invite dans {channel.mention} !",
                allowed_mentions=discord.AllowedMentions(users=[guest]),
            )
            return f"👥 {guest.mention} peut rejoindre ton salon."

        await self._run(interaction, action)

    async def transfer(self, interaction: discord.Interaction, new_owner: discord.Member) -> None:
        async def action(actor: discord.Member, channel: discord.VoiceChannel) -> str:
            await self.refresh_panel(await self.service.transfer(actor, channel, new_owner))
            return f"👑 {new_owner.mention} est maintenant propriétaire du salon."

        await self._run(interaction, action)

    async def close(self, interaction: discord.Interaction) -> None:
        actor, channel = self._context(interaction)
        await self.service.require_owned_room(actor, channel.id)
        await interaction.response.send_message("🗑️ Salon fermé.", ephemeral=True)
        await self.service.close(actor, channel)

    @vocal.command(name="rename", description="Renomme ton salon vocal")
    @app_commands.describe(nom="Nouveau nom du salon")
    async def vocal_rename(self, interaction: discord.Interaction, nom: str) -> None:
        await self.rename(interaction, nom)

    @vocal.command(name="lock", description="Verrouille ton salon (présents et invités seulement)")
    async def vocal_lock(self, interaction: discord.Interaction) -> None:
        await self.lock(interaction)

    @vocal.command(name="unlock", description="Rouvre ton salon à tout le monde")
    async def vocal_unlock(self, interaction: discord.Interaction) -> None:
        await self.unlock(interaction)

    @vocal.command(name="invite", description="Autorise quelqu'un à rejoindre ton salon")
    @app_commands.describe(membre="La personne à inviter")
    async def vocal_invite(self, interaction: discord.Interaction, membre: discord.Member) -> None:
        await self.invite(interaction, membre)

    @vocal.command(name="limit", description="Fixe le nombre de places (0 = illimité)")
    @app_commands.describe(places="Nombre de places, 0 pour illimité")
    async def vocal_limit(
        self, interaction: discord.Interaction, places: app_commands.Range[int, 0, 99]
    ) -> None:
        await self.set_limit(interaction, places)

    @vocal.command(name="transfer", description="Donne ton salon à quelqu'un qui y est")
    @app_commands.describe(membre="Le nouveau propriétaire")
    async def vocal_transfer(
        self, interaction: discord.Interaction, membre: discord.Member
    ) -> None:
        await self.transfer(interaction, membre)

    @vocal.command(name="close", description="Supprime ton salon vocal")
    async def vocal_close(self, interaction: discord.Interaction) -> None:
        await self.close(interaction)


async def setup(bot: MingatiBot) -> None:
    await bot.add_cog(Voice(bot))
