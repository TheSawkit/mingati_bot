import logging
from types import SimpleNamespace

import discord
import pytest
from discord import app_commands

from mingati.interactions import report_error


class RecordingInteraction:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.response = SimpleNamespace(is_done=lambda: False, send_message=self._send)

    async def _send(self, content: str, ephemeral: bool) -> None:
        self.sent.append(content)


def expired_interaction_error() -> app_commands.CommandInvokeError:
    response = SimpleNamespace(status=404, reason="Not Found")
    not_found = discord.NotFound(response, {"code": 10062, "message": "Unknown interaction"})
    return app_commands.CommandInvokeError(SimpleNamespace(name="refresh"), not_found)


async def test_expired_interaction_is_a_clear_warning_without_reply(
    caplog: pytest.LogCaptureFixture,
) -> None:
    interaction = RecordingInteraction()

    with caplog.at_level(logging.WARNING):
        await report_error(interaction, expired_interaction_error(), "/freegames refresh")

    assert interaction.sent == []
    assert [record.levelno for record in caplog.records] == [logging.WARNING]
    assert "3 s" in caplog.text and "DNS" in caplog.text
    assert "Traceback" not in caplog.text


async def test_unexpected_errors_are_still_logged_and_answered(
    caplog: pytest.LogCaptureFixture,
) -> None:
    interaction = RecordingInteraction()

    with caplog.at_level(logging.ERROR):
        await report_error(interaction, RuntimeError("bug"), "/x")

    assert interaction.sent and "planté" in interaction.sent[0]
    assert caplog.records[0].levelno == logging.ERROR
