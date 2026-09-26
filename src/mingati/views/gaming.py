from typing import Protocol

import discord

from mingati.interactions import MingatiView
from mingati.services.gaming_sessions import GamingSession

PLATFORMS = {
    "PC": "🖥️",
    "PlayStation": "🎮",
    "Xbox": "🎮",
    "Switch": "🕹️",
    "Mobile": "📱",
    "Cross-play": "🌐",
}


class SessionControls(Protocol):
    async def join(self, interaction: discord.Interaction) -> None: ...
    async def leave(self, interaction: discord.Interaction) -> None: ...
    async def open_voice(self, interaction: discord.Interaction) -> None: ...


def build_session_embed(session: GamingSession) -> discord.Embed:
    """'Qui joue ?' card; Discord timestamps render in each reader's own timezone."""
    lines = [f"{PLATFORMS.get(session.platform, '🎮')} {session.platform}"]
    if session.mode:
        lines.append(f"🎯 {session.mode}")
    lines.append(f"🕘 <t:{session.starts_at}:t> (<t:{session.starts_at}:R>)")
    if session.voice_channel_id:
        lines.append(f"🎙 <#{session.voice_channel_id}>")

    status = " — **Complet**" if session.is_full else ""
    lines.append(f"\n👥 **{len(session.member_ids)} / {session.max_players}**{status}")
    lines.extend(
        f"<@{user_id}>{' 👑' if user_id == session.host_id else ''}"
        for user_id in session.member_ids
    )

    return discord.Embed(
        title=f"🎮 {session.game}",
        description="\n".join(lines),
        color=discord.Color.orange() if session.is_full else discord.Color.green(),
    ).set_footer(text="Lance ta propre session avec /jouer")


class SessionView(MingatiView):
    """Persistent card buttons; the session is found from the message they are attached to."""

    def __init__(self, controls: SessionControls) -> None:
        super().__init__(timeout=None)
        self.controls = controls

    @discord.ui.button(
        label="Je rejoins", style=discord.ButtonStyle.success, custom_id="mingati:session:join"
    )
    async def join(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.join(interaction)

    @discord.ui.button(label="Je quitte", custom_id="mingati:session:leave")
    async def leave(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.leave(interaction)

    @discord.ui.button(label="Créer le vocal", emoji="🎙", custom_id="mingati:session:voice")
    async def voice(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.open_voice(interaction)
