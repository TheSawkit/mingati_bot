import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from mingati.providers.games import steam
from mingati.providers.games.base import FreeGame
from mingati.providers.games.epic import parse_epic
from mingati.providers.games.gog import giveaway_section_ids, parse_gog, parse_gog_giveaway
from mingati.providers.games.steam import (
    STEAM_SEARCH_URL,
    SteamProvider,
    parse_steam_details,
    parse_steam_search,
)
from mingati.providers.http import ProviderError

DATA = Path(__file__).parent / "data"
DURING_GIVEAWAY = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)


def load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def test_epic_keeps_only_games_free_right_now() -> None:
    games = parse_epic(load("epic_promotions.json"), DURING_GIVEAWAY)

    assert [game.title for game in games] == ["Astrea Six Sided Oracles"]
    game = games[0]
    assert game.url == "https://store.epicgames.com/fr/p/astrea-six-sided-oracles-33c949"
    assert game.ends_at == datetime(2026, 10, 1, 15, 0, tzinfo=UTC)
    assert game.image_url and game.image_url.startswith("https://")


def test_epic_giveaway_is_over_after_its_end_date() -> None:
    assert parse_epic(load("epic_promotions.json"), datetime(2026, 10, 2, tzinfo=UTC)) == []


def test_gog_keeps_paid_games_discounted_to_zero() -> None:
    games = parse_gog(load("gog_catalog.json"))

    assert [(game.title, game.url) for game in games] == [
        ("The Saboteur™", "https://www.gog.com/fr/game/saboteur")
    ]
    assert games[0].ends_at is None


def test_steam_search_extracts_unique_app_ids() -> None:
    assert parse_steam_search(load("steam_search.json")) == ["4059370", "1091500"]


def test_steam_details_keep_full_games_only() -> None:
    details = load("steam_details.json")

    assert parse_steam_details("4059370", details) is None
    game = parse_steam_details("1091500", details)
    assert game == FreeGame(
        source="steam",
        external_id="1091500",
        title="Some Game",
        url="https://store.steampowered.com/app/1091500/",
        image_url="https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/1091500/header.jpg",
    )


@pytest.mark.parametrize(
    "parse",
    [lambda p: parse_epic(p, DURING_GIVEAWAY), parse_gog, parse_steam_search],
)
def test_unexpected_payload_is_a_provider_error(parse) -> None:
    with pytest.raises(ProviderError):
        parse({"unexpected": True})


def test_offer_key_changes_when_the_same_game_is_offered_again() -> None:
    first = FreeGame("epic", "42", "Game", "https://x", ends_at=datetime(2026, 1, 1, tzinfo=UTC))
    again = FreeGame("epic", "42", "Game", "https://x", ends_at=datetime(2026, 6, 1, tzinfo=UTC))
    open_ended = FreeGame("steam", "42", "Game", "https://x")

    assert first.offer_key != again.offer_key
    assert open_ended.offer_key == "steam:42:open"


def test_gog_giveaway_sections_are_found_in_the_homepage_index() -> None:
    assert giveaway_section_ids(load("gog_sections_index.json")) == ["2"]
    assert giveaway_section_ids({"sections": []}) == []


def test_gog_giveaway_becomes_a_free_game_until_its_end_date() -> None:
    game = parse_gog_giveaway(load("gog_giveaway_section.json"), DURING_GIVEAWAY)

    assert game == FreeGame(
        source="gog",
        external_id="1207658930",
        title="Heroes of Might and Magic® 3: Complete",
        url="https://www.gog.com/fr/game/heroes_of_might_and_magic_3_complete_edition",
        image_url="https://images.gog-statics.com/giveaway-cover.png",
        ends_at=datetime(2026, 9, 29, 13, 0, tzinfo=UTC),
    )
    assert (
        parse_gog_giveaway(load("gog_giveaway_section.json"), datetime(2026, 10, 1, tzinfo=UTC))
        is None
    )


def test_gog_giveaway_without_a_usable_product_is_ignored() -> None:
    assert parse_gog_giveaway({"properties": {}}, DURING_GIVEAWAY) is None
    dlc = load("gog_giveaway_section.json")
    dlc["properties"]["product"]["productType"] = "dlc"
    assert parse_gog_giveaway(dlc, DURING_GIVEAWAY) is None


async def test_steam_details_are_fetched_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    in_flight, peak = 0, 0

    async def fake_fetch_json(http, url, params=None, headers=None):
        nonlocal in_flight, peak
        if url == STEAM_SEARCH_URL:
            return load("steam_search.json")
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        in_flight -= 1
        return load("steam_details.json")

    monkeypatch.setattr(steam, "fetch_json", fake_fetch_json)

    games = await SteamProvider("BE").fetch(http=None)

    assert [game.external_id for game in games] == ["1091500"]
    assert peak == 2
