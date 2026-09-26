from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import aiohttp


@dataclass(frozen=True, slots=True)
class FreeGame:
    source: str
    external_id: str
    title: str
    url: str
    image_url: str | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @property
    def offer_key(self) -> str:
        """Identity of one giveaway: the same game offered again later is a new offer."""
        end = int(self.ends_at.timestamp()) if self.ends_at else "open"
        return f"{self.source}:{self.external_id}:{end}"


class GameProvider(Protocol):
    name: str
    label: str

    async def fetch(self, http: aiohttp.ClientSession) -> list[FreeGame]: ...
