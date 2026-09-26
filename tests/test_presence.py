from pathlib import Path
from types import SimpleNamespace

import discord

from mingati.bot import EXTENSIONS, MingatiBot, build_intents
from mingati.config import Settings
from mingati.database import Database
from mingati.services.presence import describe_playing, group_by_game, playing_game
from mingati.utils.logging import LastErrorHandler


def member(name: str, *activities: discord.BaseActivity, bot: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        display_name=name, mention=f"<@{name}>", bot=bot, activities=list(activities)
    )


def test_only_playing_activities_count() -> None:
    listening = discord.Activity(type=discord.ActivityType.listening, name="Spotify")

    assert playing_game(member("A", listening, discord.Game("Valorant"))) == "Valorant"
    assert playing_game(member("B", listening)) is None


def test_players_are_grouped_by_game_most_played_first() -> None:
    members = [
        member("A", discord.Game("Minecraft")),
        member("B", discord.Game("Valorant")),
        member("C", discord.Game("Valorant")),
        member("D"),
        member("Bot", discord.Game("Valorant"), bot=True),
    ]

    groups = group_by_game(members)

    assert list(groups) == ["Valorant", "Minecraft"]
    assert [player.display_name for player in groups["Valorant"]] == ["B", "C"]
    assert describe_playing(members).splitlines()[1] == "• **Valorant** — <@B>, <@C>"


def test_nobody_playing_is_said_plainly() -> None:
    assert describe_playing([member("A")]) == "Personne n'est en jeu en ce moment."


def test_presence_needs_both_privileged_intents() -> None:
    intents = build_intents(Settings(discord_token="t", discord_guild_id=1, presence_enabled=True))

    assert intents.presences and intents.members
    assert not intents.message_content


async def test_en_jeu_exists_only_when_presence_is_enabled(tmp_path: Path) -> None:
    for enabled in (False, True):
        settings = Settings(discord_token="t", discord_guild_id=1, presence_enabled=enabled)
        bot = MingatiBot(settings, Database(tmp_path / "db.sqlite"), LastErrorHandler())
        async with bot:
            for extension in EXTENSIONS:
                await bot.load_extension(extension)
            assert (bot.tree.get_command("en-jeu") is not None) is enabled
