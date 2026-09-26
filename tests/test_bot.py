import importlib
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


def test_intents_are_least_privilege() -> None:
    intents = build_intents()

    assert intents.guilds
    assert not intents.message_content
    assert not intents.members
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


def test_extensions_import_cleanly() -> None:
    for extension in EXTENSIONS:
        assert hasattr(importlib.import_module(extension), "setup")


async def test_cogs_register_expected_commands_and_persistent_panel(tmp_path: Path) -> None:
    settings = Settings(discord_token="t", discord_guild_id=1)
    bot = MingatiBot(settings, Database(tmp_path / "db.sqlite"), LastErrorHandler())

    for extension in EXTENSIONS:
        await bot.load_extension(extension)

    registered = {
        group.name: sorted(command.name for command in group.commands)
        for group in bot.tree.get_commands()
        if isinstance(group, app_commands.Group)
    }
    assert registered == {
        "bot": ["status"],
        "vocal": ["close", "invite", "limit", "lock", "rename", "transfer", "unlock"],
    }
    assert all(view.is_persistent() for view in bot.persistent_views)
    assert len(bot.persistent_views) == 1
    await bot.close()
