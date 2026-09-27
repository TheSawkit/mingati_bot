import asyncio
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from mingati.providers.games.base import FreeGame
from mingati.providers.http import ProviderError, fetch_json

GOG_CATALOG_URL = "https://catalog.gog.com/v1/catalog"
GOG_HOME_SECTIONS_URL = "https://sections.gog.com/v1/pages/2f"
GOG_SECTION_URL = "https://sections.gog.com/v1/pages/2f/sections/{section_id}"
GOG_GAME_URL = "https://www.gog.com/fr/game/{slug}"
GIVEAWAY_SECTION = "GIVEAWAY_SECTION"
MAX_GIVEAWAY_SECTIONS = 3


def _amount(price: dict[str, Any], key: str) -> Decimal | None:
    try:
        return Decimal((price.get(key) or {}).get("amount", ""))
    except InvalidOperation:
        return None


def parse_gog(payload: dict[str, Any]) -> list[FreeGame]:
    """Paid games temporarily discounted to zero in the catalog (no end date given)."""
    try:
        products = payload["products"]
    except (KeyError, TypeError) as error:
        raise ProviderError("Unexpected GOG catalog payload") from error

    games = []
    for product in products:
        price = product.get("price") or {}
        final, base = _amount(price, "finalMoney"), _amount(price, "baseMoney")
        if final != 0 or not base or not product.get("storeLink"):
            continue
        games.append(
            FreeGame(
                source="gog",
                external_id=str(product["id"]),
                title=str(product["title"]),
                url=product["storeLink"],
                image_url=product.get("coverHorizontal"),
            )
        )
    return games


def giveaway_section_ids(index: dict[str, Any]) -> list[str]:
    """IDs of the homepage giveaway banners, where GOG offers most of its free games."""
    try:
        sections = index["sections"]
    except (KeyError, TypeError) as error:
        raise ProviderError("Unexpected GOG homepage sections payload") from error
    return [
        str(section["sectionId"])
        for section in sections
        if section.get("sectionType") == GIVEAWAY_SECTION and section.get("sectionId")
    ][:MAX_GIVEAWAY_SECTIONS]


def _end_date(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(str(raw)).astimezone(UTC)
    except ValueError:
        return None


def parse_gog_giveaway(section: dict[str, Any], now: datetime) -> FreeGame | None:
    """The giveaway's game while it can still be claimed; None for anything else."""
    properties = section.get("properties") or {}
    product = properties.get("product") or {}
    ends_at = _end_date(properties.get("endDate"))
    if product.get("productType") != "game" or not product.get("slug") or not product.get("id"):
        return None
    if ends_at is not None and ends_at <= now:
        return None
    return FreeGame(
        source="gog",
        external_id=str(product["id"]),
        title=str(product.get("title", "")),
        url=GOG_GAME_URL.format(slug=product["slug"]),
        image_url=product.get("coverHorizontal"),
        ends_at=ends_at,
    )


class GogProvider:
    name = "gog"
    label = "GOG"

    def __init__(self, country: str) -> None:
        self.country = country

    async def fetch(self, http: aiohttp.ClientSession) -> list[FreeGame]:
        giveaways, discounted = await asyncio.gather(self._giveaways(http), self._discounted(http))
        unique = {game.external_id: game for game in [*discounted, *giveaways]}
        return list(unique.values())

    async def _giveaways(self, http: aiohttp.ClientSession) -> list[FreeGame]:
        params = {"countryCode": self.country, "locale": "fr-FR", "currencyCode": "EUR"}
        index = await fetch_json(http, GOG_HOME_SECTIONS_URL, params)
        sections = await asyncio.gather(
            *(
                fetch_json(http, GOG_SECTION_URL.format(section_id=section_id), params)
                for section_id in giveaway_section_ids(index)
            )
        )
        now = datetime.now(UTC)
        games = (parse_gog_giveaway(section, now) for section in sections)
        return [game for game in games if game is not None]

    async def _discounted(self, http: aiohttp.ClientSession) -> list[FreeGame]:
        params = {
            "limit": "48",
            "price": "between:0,0",
            "discounted": "eq:true",
            "productType": "in:game,pack",
            "countryCode": self.country,
            "locale": "fr-FR",
            "currencyCode": "EUR",
        }
        return parse_gog(await fetch_json(http, GOG_CATALOG_URL, params))
