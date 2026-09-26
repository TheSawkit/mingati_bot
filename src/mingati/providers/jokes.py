from dataclasses import dataclass
from typing import Any

import aiohttp
from pydantic import SecretStr

from mingati.config import Settings
from mingati.providers.http import ProviderError, fetch_json

BLAGUES_API_URL = "https://www.blagues-api.fr/api/random"
EXCLUDED_CATEGORIES = ("dark", "limit")


@dataclass(frozen=True, slots=True)
class Joke:
    setup: str
    punchline: str


def parse_blague(payload: dict[str, Any]) -> Joke:
    try:
        return Joke(setup=str(payload["joke"]).strip(), punchline=str(payload["answer"]).strip())
    except (KeyError, TypeError) as error:
        raise ProviderError("Unexpected Blagues API payload") from error


def create_joke_provider(settings: Settings) -> "BlaguesApiProvider | None":
    """blagues-api.fr when BLAGUES_API_TOKEN is set, otherwise None (AI and built-in fallbacks)."""
    return BlaguesApiProvider(settings.blagues_api_token) if settings.blagues_api_token else None


class BlaguesApiProvider:
    """Random French jokes from blagues-api.fr, without the dark and borderline categories."""

    def __init__(self, token: SecretStr) -> None:
        self._token = token

    async def random(self, http: aiohttp.ClientSession) -> Joke:
        params = [("disallow", category) for category in EXCLUDED_CATEGORIES]
        headers = {"Authorization": f"Bearer {self._token.get_secret_value()}"}
        return parse_blague(await fetch_json(http, BLAGUES_API_URL, params, headers))
