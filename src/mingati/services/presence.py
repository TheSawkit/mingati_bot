from collections.abc import Iterable

import discord

MAX_GAMES = 15


def playing_game(member: discord.Member) -> str | None:
    """Name of the game the member is currently playing, if any."""
    for activity in member.activities:
        if activity.type is discord.ActivityType.playing and activity.name:
            return activity.name
    return None


def group_by_game(members: Iterable[discord.Member]) -> dict[str, list[discord.Member]]:
    """Humans currently in a game, grouped by game, most played first."""
    groups: dict[str, list[discord.Member]] = {}
    for member in members:
        game = None if member.bot else playing_game(member)
        if game:
            groups.setdefault(game, []).append(member)
    ordered = sorted(groups.items(), key=lambda item: (-len(item[1]), item[0].casefold()))
    return dict(ordered[:MAX_GAMES])


def describe_playing(members: Iterable[discord.Member]) -> str:
    groups = group_by_game(members)
    if not groups:
        return "Personne n'est en jeu en ce moment."
    lines = [
        f"• **{game}** — {', '.join(player.mention for player in players)}"
        for game, players in groups.items()
    ]
    return "\n".join(["🕹️ **En jeu maintenant**", *lines])
