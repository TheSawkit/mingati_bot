import re
from typing import Any

import aiohttp

from mingati.providers.games.base import FreeGame
from mingati.providers.http import ProviderError, fetch_json

STEAM_SEARCH_URL = "https://store.steampowered.com/search/results/"
STEAM_DETAILS_URL = "https://store.steampowered.com/api/appdetails"
STEAM_APP_URL = "https://store.steampowered.com/app/{appid}/"
APP_ID_IN_ASSET_URL = re.compile(r"/apps/(\d+)/")
GAMES_CATEGORY = "998"


def parse_steam_search(payload: dict[str, Any]) -> list[str]:
    """App IDs of the search results, read from their image URLs (the JSON has no ID field)."""
    try:
        items = payload["items"]
    except (KeyError, TypeError) as error:
        raise ProviderError("Unexpected Steam search payload") from error
    app_ids = (APP_ID_IN_ASSET_URL.search(item.get("logo", "")) for item in items)
    return list(dict.fromkeys(match.group(1) for match in app_ids if match))


def parse_steam_details(app_id: str, payload: dict[str, Any]) -> FreeGame | None:
    """The app as a free game when it is a full game at a 100 % discount."""
    entry = payload.get(app_id) or {}
    data = entry.get("data") or {}
    discount = (data.get("price_overview") or {}).get("discount_percent")
    if not entry.get("success") or data.get("type") != "game" or discount != 100:
        return None
    return FreeGame(
        source="steam",
        external_id=app_id,
        title=str(data["name"]),
        url=STEAM_APP_URL.format(appid=app_id),
        image_url=data.get("header_image"),
    )


class SteamProvider:
    name = "steam"
    label = "Steam"

    def __init__(self, country: str) -> None:
        self.country = country

    async def fetch(self, http: aiohttp.ClientSession) -> list[FreeGame]:
        search = {
            "json": "1",
            "maxprice": "free",
            "specials": "1",
            "category1": GAMES_CATEGORY,
            "count": "50",
            "cc": self.country,
        }
        games = []
        for app_id in parse_steam_search(await fetch_json(http, STEAM_SEARCH_URL, search)):
            details = {
                "appids": app_id,
                "cc": self.country,
                "l": "french",
                "filters": "basic,price_overview",
            }
            game = parse_steam_details(app_id, await fetch_json(http, STEAM_DETAILS_URL, details))
            if game:
                games.append(game)
        return games
