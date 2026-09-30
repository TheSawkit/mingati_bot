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
    """Application service: validates input and delegates to the configured provider."""

    def __init__(self, provider: TMDBProvider | None) -> None:
        self.provider = provider

    def _provider(self) -> TMDBProvider:
        if self.provider is None:
            raise UserFacingError(
                "La recherche de films/séries n'est pas configurée. "
                "Ajoute TMDB_API_TOKEN dans ton .env."
            )
        return self.provider

    async def search(self, http: aiohttp.ClientSession, query: str) -> list[MediaSearchResult]:
        query = query.strip()
        if len(query) < 2:
            raise UserFacingError("Donne-moi au moins 2 caractères pour la recherche.")

        provider = self._provider()
        results = await provider.search(http, query)
        if not results:
            return []

        primary = results[0]
        query_key = query.casefold()
        exact_titles = {primary.title.casefold()}
        if primary.original_title:
            exact_titles.add(primary.original_title.casefold())
        if query_key in exact_titles:
            return [primary]

        collections = await provider.search_collections(http, query)
        if collections:
            collection = await self.collection(http, collections[0].id)
            if collection.films:
                return list(collection.films[:25])

        return results[:25]

    async def details(
        self,
        http: aiohttp.ClientSession,
        result: MediaSearchResult,
    ) -> MediaDetails:
        return await self._provider().details(http, result.media_type, result.id)

    async def collection(
        self,
        http: aiohttp.ClientSession,
        collection_id: int,
    ) -> CollectionDetails:
        return await self._provider().collection(http, collection_id)

    async def season(
        self,
        http: aiohttp.ClientSession,
        series_id: int,
        season_number: int,
    ) -> SeasonDetails:
        if season_number < 1:
            raise UserFacingError("Cette saison n'existe pas.")
        return await self._provider().season(http, series_id, season_number)

    async def providers(
        self,
        http: aiohttp.ClientSession,
        media: MediaDetails,
    ) -> list[WatchProvider]:
        return await self._provider().providers(http, media.media_type, media.id)
