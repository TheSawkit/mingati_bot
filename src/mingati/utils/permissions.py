from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import TYPE_CHECKING, TypeVar

import discord
from discord import app_commands

if TYPE_CHECKING:
    from mingati.bot import MingatiBot

T = TypeVar("T")


def has_any_role(role_ids: Iterable[int], allowed: frozenset[int]) -> bool:
    """True when at least one of the member's roles is in the allowed set."""
    return not allowed.isdisjoint(role_ids)


def staff_only() -> Callable[[T], T]:
    """App command check restricting a command to the staff/moderator roles from settings."""

    async def predicate(interaction: discord.Interaction[MingatiBot]) -> bool:
        allowed = interaction.client.settings.staff_role_ids
        member = interaction.user
        if isinstance(member, discord.Member) and has_any_role(
            (role.id for role in member.roles), allowed
        ):
            return True
        raise app_commands.MissingAnyRole(list(allowed))

    return app_commands.check(predicate)
