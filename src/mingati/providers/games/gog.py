from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from mingati.providers.games.base import FreeGame
from mingati.providers.http import ProviderError, fetch_json

GOG_CATALOG_URL = "https://catalog.gog.com/v1/catalog"


def _amount(price: dict[str, Any], key: str) -> Decimal | None:
    try:
        return Decimal((price.get(key) or {}).get("amount", ""))
    except InvalidOperation:
        return None


def parse_gog(payload: dict[str, Any]) -> list[FreeGame]:
    """Paid games temporarily discounted to zero (GOG gives no end date in its catalog)."""
    try:
        products = payload["products"]
    except (KeyError, TypeError) as error:
        raise ProviderError("Unexpected GOG payload") from error

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


class GogProvider:
    name = "gog"
    label = "GOG"

    def __init__(self, country: str) -> None:
        self.country = country

    async def fetch(self, http: aiohttp.ClientSession) -> list[FreeGame]:
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
