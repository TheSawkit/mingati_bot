import asyncio
from typing import Any

import aiohttp

from mingati import __version__

USER_AGENT = f"MingatiBot/{__version__} (+https://github.com/TheSawkit/mingati_bot)"
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=20)
RETRY_DELAYS_SECONDS: tuple[float, ...] = (2, 5)


class ProviderError(Exception):
    """An external API could not be reached or answered something unusable."""


def create_http_session() -> aiohttp.ClientSession:
    """Shared HTTP client with a total timeout, so no external call can hang the bot."""
    return aiohttp.ClientSession(timeout=REQUEST_TIMEOUT, headers={"User-Agent": USER_AGENT})


async def fetch_json(
    session: aiohttp.ClientSession, url: str, params: dict[str, str] | None = None
) -> Any:
    """GET JSON, retrying network errors and 5xx a few times; 4xx fail immediately."""
    last_error: BaseException | None = None
    for delay in (*RETRY_DELAYS_SECONDS, None):
        try:
            async with session.get(url, params=params) as response:
                if response.status < 500:
                    response.raise_for_status()
                    return await response.json(content_type=None)
                last_error = ProviderError(f"{url} answered HTTP {response.status}")
        except (aiohttp.ClientConnectionError, TimeoutError) as error:
            last_error = error
        if delay is None:
            break
        await asyncio.sleep(delay)
    raise ProviderError(f"{url} is unreachable") from last_error
