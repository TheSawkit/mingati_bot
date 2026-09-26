import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from mingati.errors import UserFacingError
from mingati.services.fun import (
    EIGHT_BALL_ANSWERS,
    flip_coin,
    pick_game,
    pull_trigger,
    roll_dice,
    shake_eight_ball,
    split_choices,
)
from mingati.services.game_night import parse_day, plan_game_night

BRUSSELS = ZoneInfo("Europe/Brussels")
NOW = datetime(2026, 9, 26, 18, 0, tzinfo=BRUSSELS)


def test_dice_stay_in_range() -> None:
    rolls = roll_dice(6, 10, random.Random(1))

    assert len(rolls) == 10
    assert all(1 <= roll <= 6 for roll in rolls)


@pytest.mark.parametrize(("faces", "count"), [(1, 1), (6, 0), (6, 11), (1001, 1)])
def test_invalid_dice_are_refused(faces: int, count: int) -> None:
    with pytest.raises(UserFacingError):
        roll_dice(faces, count, random.Random(1))


def test_coin_eight_ball_and_roulette_use_known_outcomes() -> None:
    rng = random.Random(3)

    assert flip_coin(rng) in ("Pile", "Face")
    assert shake_eight_ball(rng) in EIGHT_BALL_ANSWERS
    shots = [pull_trigger(rng) for _ in range(600)]
    assert 50 < sum(shots) < 150


def test_random_game_choices_are_cleaned_and_deduplicated() -> None:
    assert split_choices(" Valorant , LoL;valorant ; Valorant,  ") == ["Valorant", "LoL"]
    assert pick_game("Valorant, LoL", random.Random(0)) in ("Valorant", "LoL")
    with pytest.raises(UserFacingError, match="deux jeux"):
        pick_game("Valorant, Valorant", random.Random(0))


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("aujourd'hui", NOW.date()),
        ("demain", NOW.date() + timedelta(days=1)),
        ("27/09", datetime(2026, 9, 27).date()),
        ("01/01", datetime(2027, 1, 1).date()),
        ("03/10/2026", datetime(2026, 10, 3).date()),
    ],
)
def test_parse_day(raw: str, expected) -> None:
    assert parse_day(raw, NOW.date()) == expected


@pytest.mark.parametrize("raw", ["samedi", "31/02", "2026-09-27"])
def test_parse_day_rejects_unknown_formats(raw: str) -> None:
    with pytest.raises(UserFacingError):
        parse_day(raw, NOW.date())


def test_game_night_is_planned_in_the_server_timezone() -> None:
    night = plan_game_night(
        game=" Among   Us ",
        day="demain",
        time="21h",
        players=8,
        description="  Ramenez  vos micros ",
        host_name="Alice",
        now=NOW,
    )

    assert night.starts_at == datetime(2026, 9, 27, 21, 0, tzinfo=BRUSSELS)
    assert night.ends_at - night.starts_at == timedelta(hours=3)
    assert night.event_name == "🎮 Game night : Among Us"
    assert "👥 8 joueurs · organisé par Alice" in night.event_description
    assert "Ramenez vos micros" in night.event_description


@pytest.mark.parametrize(
    ("day", "time", "message"),
    [
        ("aujourd'hui", "18h05", "10 minutes"),
        ("aujourd'hui", "17h", "10 minutes"),
        ("26/12/2026", "21h", "60 jours"),
    ],
)
def test_game_night_time_window_is_enforced(day: str, time: str, message: str) -> None:
    with pytest.raises(UserFacingError, match=message):
        plan_game_night(
            game="Among Us",
            day=day,
            time=time,
            players=4,
            description=None,
            host_name="Alice",
            now=NOW,
        )
