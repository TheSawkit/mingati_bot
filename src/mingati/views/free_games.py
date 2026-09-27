from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import discord

from mingati.providers.games import FreeGame
from mingati.services.free_games import SourceStatus


@dataclass(frozen=True, slots=True)
class PlatformStyle:
    """Visual identity of a store: every announcement from it looks the same."""

    label: str
    color: discord.Color
    emoji_name: str
    fallback_emoji: str = "🎮"


PLATFORMS = {
    "epic": PlatformStyle("Epic Games", discord.Color(0x2F2F2F), "epic_games"),
    "steam": PlatformStyle("Steam", discord.Color(0x1B2838), "steam"),
    "gog": PlatformStyle("GOG", discord.Color(0x86328A), "gog"),
}
UNKNOWN_PLATFORM = PlatformStyle("Boutique", discord.Color.green(), "", "🎁")


@dataclass(frozen=True, slots=True)
class Announcement:
    content: str
    embed: discord.Embed
    view: discord.ui.View


def platform_style(source: str) -> PlatformStyle:
    return PLATFORMS.get(source, UNKNOWN_PLATFORM)


def platform_label(source: str) -> str:
    return platform_style(source).label


def find_logo(emojis: Iterable[Any], style: PlatformStyle) -> Any | None:
    """The server's custom emoji for this store, looked up by name (IDs never hardcoded)."""
    return next((emoji for emoji in emojis if emoji.name == style.emoji_name), None)


def _offer_end(game: FreeGame) -> str:
    if game.ends_at is None:
        return "Date de fin non communiquée par la boutique : ne traîne pas !"
    end = discord.utils.format_dt(game.ends_at, "F")
    return f"{end} ({discord.utils.format_dt(game.ends_at, 'R')})"


def build_announcement(game: FreeGame, logo: Any | None) -> Announcement:
    """Store-branded post of one free game: logo, colors, end date and a claim button."""
    style = platform_style(game.source)
    icon = str(logo) if logo else style.fallback_emoji
    embed = discord.Embed(title=game.title, url=game.url, color=style.color)
    embed.set_author(name=style.label, icon_url=logo.url if logo else None)
    embed.add_field(name="⏳ Fin de l'offre", value=_offer_end(game), inline=False)
    if game.image_url:
        embed.set_image(url=game.image_url)
    embed.set_footer(text="Mingati · jeux gratuits")

    view = discord.ui.View(timeout=None)
    claim = discord.ui.Button(
        label=f"Récupérer sur {style.label}",
        url=game.url,
        emoji=discord.PartialEmoji.from_str(icon),
    )
    view.add_item(claim)
    content = f"{icon} Nouveau jeu gratuit sur **{style.label}** !"
    return Announcement(content=content, embed=embed, view=view)


def build_status_embed(statuses: list[SourceStatus], active: list[FreeGame]) -> discord.Embed:
    """Staff view of every source's health and of the offers currently running."""
    embed = discord.Embed(title="🎁 Jeux gratuits — état", color=discord.Color.green())
    for status in statuses:
        lines = [
            "✅ "
            + discord.utils.format_dt(status.last_success_at, "R")
            + f" · {status.last_count} jeu(x)"
            if status.last_success_at
            else "Jamais récupéré"
        ]
        if status.last_error and status.last_error_at:
            when = discord.utils.format_dt(status.last_error_at, "R")
            lines.append(f"⚠️ {when} : {status.last_error[:150]}")
        embed.add_field(name=status.label, value="\n".join(lines), inline=False)
    current = "\n".join(
        f"• [{game.title}]({game.url}) — {platform_label(game.source)}" for game in active
    )
    embed.add_field(name="En ce moment", value=current[:1024] or "Aucun jeu gratuit", inline=False)
    return embed
