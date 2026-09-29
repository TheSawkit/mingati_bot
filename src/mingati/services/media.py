from __future__ import annotations

import aiohttp

from mingati.errors import UserFacingError
from mingati.providers.media.tmdb import (
    CollectionDetails,
    MediaDetails,
    MediaSearchResult,
    SeasonDetails,
    TMDBProvider,
    WatchProvider,
)


class MediaService:
    """Business orchestration for movie and TV lookup."""

    def __init__(self, provider: TMDBProvider | None) -> None:
        self.provider = provider

    def _require_provider(self) -> TMDBProvider:
        if self.provider is None:
            raise UserFacingError(
                "La recherche de films/séries n'est pas configurée. "
                "Ajoute TMDB_API_TOKEN dans ton .env."
            )
        return self.provider

    async def search(
        self,
        http: aiohttp.ClientSession,
        query: str,
    ) -> list[MediaSearchResult]:
        if len(query.strip()) < 2:
            raise UserFacingError("Donne-moi au moins 2 caractères pour la recherche.")
        return await self._require_provider().search(http, query)

    async def details(
        self,
        http: aiohttp.ClientSession,
        result: MediaSearchResult,
    ) -> MediaDetails:
        return await self._require_provider().details(http, result.media_type, result.id)

    async def collection(
        self,
        http: aiohttp.ClientSession,
        collection_id: int,
    ) -> CollectionDetails:
        return await self._require_provider().collection(http, collection_id)

    async def season(
        self,
        http: aiohttp.ClientSession,
        series_id: int,
        season_number: int,
    ) -> SeasonDetails:
        return await self._require_provider().season(http, series_id, season_number)

    async def providers(
        self,
        http: aiohttp.ClientSession,
        media: MediaDetails,
    ) -> list[WatchProvider]:
        return await self._require_provider().providers(http, media.media_type, media.id)
