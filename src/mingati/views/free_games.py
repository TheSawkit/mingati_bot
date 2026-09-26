import discord

from mingati.providers.games import FreeGame
from mingati.services.free_games import SourceStatus

PLATFORMS = {
    "epic": ("Epic Games", discord.Color.dark_grey()),
    "steam": ("Steam", discord.Color.dark_blue()),
    "gog": ("GOG", discord.Color.purple()),
}


def platform_label(source: str) -> str:
    return PLATFORMS.get(source, (source, None))[0]


def build_free_game_embed(game: FreeGame) -> discord.Embed:
    """Announcement of one free game, with its end date in each reader's timezone."""
    label, color = PLATFORMS.get(game.source, (game.source, discord.Color.green()))
    embed = discord.Embed(
        title=game.title,
        url=game.url,
        description=f"🎁 Gratuit sur **{label}** !",
        color=color,
    )
    if game.ends_at:
        embed.add_field(
            name="⏳ Jusqu'au",
            value=f"{discord.utils.format_dt(game.ends_at, 'F')} "
            f"({discord.utils.format_dt(game.ends_at, 'R')})",
        )
    if game.image_url:
        embed.set_image(url=game.image_url)
    return embed.set_footer(text=label)


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
