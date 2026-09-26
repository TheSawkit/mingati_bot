from datetime import timedelta

from mingati.cogs.core import format_uptime


def test_format_uptime() -> None:
    assert format_uptime(timedelta(seconds=59)) == "0 min"
    assert format_uptime(timedelta(hours=3, minutes=14)) == "3 h 14 min"
    assert format_uptime(timedelta(days=2, minutes=5)) == "2 j 0 h 5 min"
