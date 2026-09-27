from datetime import timedelta
from types import SimpleNamespace

from mingati.cogs.core import describe_providers, format_uptime


def test_format_uptime() -> None:
    assert format_uptime(timedelta(seconds=59)) == "0 min"
    assert format_uptime(timedelta(hours=3, minutes=14)) == "3 h 14 min"
    assert format_uptime(timedelta(days=2, minutes=5)) == "2 j 0 h 5 min"


def test_providers_summary_shows_what_is_configured() -> None:
    ai = SimpleNamespace(name="groq", model="openai/gpt-oss-120b")

    assert describe_providers(
        ai, object(), ["Epic Games", "Steam"], ["Minecraft Java"]
    ).splitlines() == [
        "IA : groq · `openai/gpt-oss-120b`",
        "Blagues : blagues-api.fr",
        "Jeux gratuits : Epic Games, Steam",
        "Serveurs : Minecraft Java",
    ]
    assert describe_providers(None, None, [], []).splitlines()[:2] == [
        "IA : désactivée",
        "Blagues : secours (IA / liste)",
    ]
