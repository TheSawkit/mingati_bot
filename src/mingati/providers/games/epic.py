from datetime import UTC, datetime
from typing import Any

import aiohttp

from mingati.providers.games.base import FreeGame
from mingati.providers.http import ProviderError, fetch_json

EPIC_PROMOTIONS_URL = "https://store-site-backend-static-ipv4.ak.epicgames.com/freeGamesPromotions"
EPIC_STORE_URL = "https://store.epicgames.com/fr/p/{slug}"
PREFERRED_IMAGES = ("OfferImageWide", "Thumbnail")


def _free_window(element: dict[str, Any], now: datetime) -> tuple[datetime, datetime] | None:
    groups = (element.get("promotions") or {}).get("promotionalOffers") or []
    for offer in (offer for group in groups for offer in group.get("promotionalOffers", [])):
        if (offer.get("discountSetting") or {}).get("discountPercentage") != 0:
            continue
        start = datetime.fromisoformat(offer["startDate"])
        end = datetime.fromisoformat(offer["endDate"])
        if start <= now < end:
            return start, end
    return None


def _page_slug(element: dict[str, Any]) -> str | None:
    mappings = (element.get("offerMappings") or []) + (
        (element.get("catalogNs") or {}).get("mappings") or []
    )
    for mapping in mappings:
        if mapping.get("pageType") == "productHome" and mapping.get("pageSlug"):
            return mapping["pageSlug"]
    product_slug = element.get("productSlug")
    return product_slug.removesuffix("/home") if product_slug else None


def _image(element: dict[str, Any]) -> str | None:
    images = {image.get("type"): image.get("url") for image in element.get("keyImages") or []}
    return next((images[kind] for kind in PREFERRED_IMAGES if images.get(kind)), None)


def parse_epic(payload: dict[str, Any], now: datetime) -> list[FreeGame]:
    """Games whose current promotion makes them free right now."""
    try:
        elements = payload["data"]["Catalog"]["searchStore"]["elements"]
    except (KeyError, TypeError) as error:
        raise ProviderError("Unexpected Epic Games payload") from error

    games = []
    for element in elements:
        price = ((element.get("price") or {}).get("totalPrice") or {}).get("discountPrice")
        window = _free_window(element, now)
        slug = _page_slug(element)
        if price != 0 or window is None or slug is None:
            continue
        games.append(
            FreeGame(
                source="epic",
                external_id=str(element["id"]),
                title=str(element["title"]),
                url=EPIC_STORE_URL.format(slug=slug),
                image_url=_image(element),
                starts_at=window[0],
                ends_at=window[1],
            )
        )
    return games


class EpicProvider:
    name = "epic"
    label = "Epic Games"

    def __init__(self, country: str) -> None:
        self.country = country

    async def fetch(self, http: aiohttp.ClientSession) -> list[FreeGame]:
        params = {"locale": "fr", "country": self.country, "allowCountries": self.country}
        payload = await fetch_json(http, EPIC_PROMOTIONS_URL, params)
        return parse_epic(payload, datetime.now(UTC))
