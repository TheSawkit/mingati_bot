from typing import Protocol

import discord

from mingati.interactions import MingatiModal, MingatiView
from mingati.providers.games import FreeGame
from mingati.services.billy import MAX_QUESTION_LENGTH
from mingati.services.gaming_sessions import GamingSession
from mingati.views.free_games import platform_label

MAX_LISTED = 10


class HubControls(Protocol):
    async def show_sessions(self, interaction: discord.Interaction) -> None: ...
    async def show_voice(self, interaction: discord.Interaction) -> None: ...
    async def show_free_games(self, interaction: discord.Interaction) -> None: ...
    async def ask_billy(self, interaction: discord.Interaction, question: str) -> None: ...


def build_hub_embed() -> discord.Embed:
    """The permanent Mingati panel."""
    return discord.Embed(
        title="🎮 MINGATI",
        description=(
            "**Qu'est-ce qu'on fait ?**\n\n"
            "🎮 **Qui joue ?** — les parties qui cherchent du monde\n"
            "🔊 **Créer un vocal** — ton salon perso en un clic\n"
            "🎁 **Jeux gratuits** — ce qui est offert en ce moment\n"
            "🤖 **Billy** — pose-lui une question (il stresse un peu)"
        ),
        color=discord.Color.blurple(),
    ).set_footer(text="Les réponses ne sont visibles que par toi")


def describe_sessions(sessions: list[GamingSession], guild_id: int) -> str:
    if not sessions:
        return "Personne ne cherche de joueurs pour l'instant. Lance une partie avec `/jouer` !"
    lines = [
        f"• **{session.game}** — {len(session.member_ids)}/{session.max_players} · "
        f"<t:{session.starts_at}:t> · "
        f"[voir](https://discord.com/channels/{guild_id}/{session.channel_id}/{session.message_id})"
        for session in sessions[:MAX_LISTED]
    ]
    return "\n".join(["🎮 **Parties en cours**", *lines])


def describe_free_games(games: list[FreeGame]) -> str:
    if not games:
        return "Aucun jeu gratuit repéré en ce moment."
    lines = [
        f"• [{game.title}]({game.url}) — {platform_label(game.source)}"
        + (f" · jusqu'au <t:{int(game.ends_at.timestamp())}:d>" if game.ends_at else "")
        for game in games[:MAX_LISTED]
    ]
    return "\n".join(["🎁 **Gratuit en ce moment**", *lines])


def describe_voice_triggers(trigger_ids: frozenset[int]) -> str:
    if not trigger_ids:
        return "Aucun salon « Créer un vocal » n'est configuré."
    channels = " ou ".join(f"<#{channel_id}>" for channel_id in sorted(trigger_ids))
    return f"🔊 Rejoins {channels} : ton salon est créé et tu y es déplacé automatiquement."


class BillyQuestionModal(MingatiModal, title="Demander à Billy"):
    question: discord.ui.TextInput["BillyQuestionModal"] = discord.ui.TextInput(
        label="Ta question", style=discord.TextStyle.paragraph, max_length=MAX_QUESTION_LENGTH
    )

    def __init__(self, controls: HubControls) -> None:
        super().__init__()
        self.controls = controls

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await self.controls.ask_billy(interaction, self.question.value)


class HubView(MingatiView):
    """Persistent hub buttons; every answer is ephemeral so the channel stays clean."""

    def __init__(self, controls: HubControls) -> None:
        super().__init__(timeout=None)
        self.controls = controls

    @discord.ui.button(label="Qui joue ?", emoji="🎮", custom_id="mingati:hub:sessions")
    async def sessions(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.show_sessions(interaction)

    @discord.ui.button(label="Créer un vocal", emoji="🔊", custom_id="mingati:hub:voice")
    async def voice(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.show_voice(interaction)

    @discord.ui.button(label="Jeux gratuits", emoji="🎁", custom_id="mingati:hub:free_games")
    async def free_games(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await self.controls.show_free_games(interaction)

    @discord.ui.button(label="Billy", emoji="🤖", custom_id="mingati:hub:billy")
    async def billy(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.send_modal(BillyQuestionModal(self.controls))
