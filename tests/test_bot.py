from pathlib import Path
from types import SimpleNamespace

import pytest
from discord import app_commands

from mingati.bot import EXTENSIONS, MingatiBot, build_intents
from mingati.config import Settings
from mingati.database import Database
from mingati.errors import UserFacingError
from mingati.interactions import describe_error
from mingati.utils.logging import LastErrorHandler
from mingati.utils.permissions import has_any_role


def test_intents_are_least_privilege_by_default() -> None:
    intents = build_intents(Settings(discord_token="t", discord_guild_id=1))

    assert intents.guilds and intents.voice_states
    assert not intents.guild_messages
    assert not intents.message_content
    assert not intents.members
    assert not intents.presences


def test_optional_features_opt_in_to_their_intent_only() -> None:
    settings = Settings(
        discord_token="t", discord_guild_id=1, billy_mentions_enabled=True, welcome_enabled=True
    )

    intents = build_intents(settings)

    assert intents.guild_messages and intents.members
    assert not intents.message_content
    assert not intents.presences


def test_user_facing_error_message_is_forwarded() -> None:
    command = SimpleNamespace(name="vocal")
    error = app_commands.CommandInvokeError(
        command, UserFacingError("Ce salon ne t'appartient pas.")
    )

    assert describe_error(error) == "Ce salon ne t'appartient pas."


def test_missing_role_is_explained() -> None:
    assert (
        describe_error(app_commands.MissingAnyRole([1])) == "Cette commande est réservée au staff."
    )


def test_unexpected_error_has_no_user_message() -> None:
    assert describe_error(app_commands.AppCommandError("bug")) is None


@pytest.mark.parametrize(
    ("roles", "allowed", "expected"),
    [({1, 2}, frozenset({2}), True), ({1}, frozenset({2}), False), ({1}, frozenset(), False)],
)
def test_has_any_role(roles: set[int], allowed: frozenset[int], expected: bool) -> None:
    assert has_any_role(roles, allowed) is expected


async def test_cogs_register_expected_commands_and_persistent_views(tmp_path: Path) -> None:
    settings = Settings(discord_token="t", discord_guild_id=1)
    bot = MingatiBot(settings, Database(tmp_path / "db.sqlite"), LastErrorHandler())

    async with bot:
        for extension in EXTENSIONS:
            await bot.load_extension(extension)

        commands = {
            command.name: sorted(sub.name for sub in getattr(command, "commands", []))
            for command in bot.tree.get_commands()
        }
        assert commands == {
            "bot": ["status"],
            "vocal": ["close", "invite", "limit", "lock", "rename", "transfer", "unlock"],
            "jouer": [],
            "freegames": ["refresh", "status"],
            "billy": [],
            "blague": [],
            "mingati": [],
            "dé": [],
            "coinflip": [],
            "8ball": [],
            "roulette": [],
            "random-game": [],
            "game-night": [],
            "server": ["add", "remove", "status"],
        }
        assert len(bot.persistent_views) == 3
        assert all(view.is_persistent() for view in bot.persistent_views)
