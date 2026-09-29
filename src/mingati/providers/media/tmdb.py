from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import aiohttp

from mingati.errors import UserFacingError
from mingati.providers.http import ProviderError, fetch_json

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500"

WATCH_CATEGORY_LABELS = {
    "flatrate": "Streaming",
    "free": "Gratuit",
    "ads": "Avec publicité",
    "rent": "Location",
    "buy": "Achat",
}


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"
    COLLECTION = "collection"


@dataclass(frozen=True, slots=True)
class MediaSearchResult:
    id: int
    media_type: MediaType
    title: str
    original_title: str | None
    year: int | None
    poster_url: str | None
    overview: str | None = None
    collection_id: int | None = None


@dataclass(frozen=True, slots=True)
class MediaDetails:
    id: int
    media_type: MediaType
    title: str
    original_title: str | None
    overview: str | None
    year: int | None
    runtime_minutes: int | None
    poster_url: str | None
    backdrop_url: str | None
    genres: tuple[str, ...]
    rating: float | None
    collection_id: int | None
    collection_name: str | None
    number_of_seasons: int | None
    number_of_episodes: int | None
    tmdb_url: str


@dataclass(frozen=True, slots=True)
class CollectionDetails:
    id: int
    name: str
    overview: str | None
    poster_url: str | None
    parts: tuple[MediaSearchResult, ...]
    tmdb_url: str


@dataclass(frozen=True, slots=True)
class Episode:
    id: int
    episode_number: int
    name: str
    overview: str | None
    runtime_minutes: int | None
    air_date: str | None
    still_url: str | None


@dataclass(frozen=True, slots=True)
class SeasonDetails:
    series_id: int
    season_number: int
    name: str
    overview: str | None
    poster_url: str | None
    episodes: tuple[Episode, ...]


@dataclass(frozen=True, slots=True)
class WatchProvider:
    provider_id: int
    provider_name: str
    category: str
    link: str
    logo_url: str | None = None


def image_url(file_path: str | None) -> str | None:
    return f"{TMDB_IMAGE_URL}{file_path.lstrip('/')}" if file_path else None


def _year(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value[:4])
    except (TypeError, ValueError):
        return None


def _title(payload: dict[str, Any], media_type: MediaType) -> str:
    return str(payload.get("title") or payload.get("name") or "")


def _original_title(payload: dict[str, Any]) -> str | None:
    value = payload.get("original_title") or payload.get("original_name")
    return str(value) if value else None


def _year_from_payload(payload: dict[str, Any], media_type: MediaType) -> int | None:
    key = "release_date" if media_type == MediaType.MOVIE else "first_air_date"
    return _year(payload.get(key))


def _runtime(details: dict[str, Any], media_type: MediaType) -> int | None:
    if media_type == MediaType.MOVIE:
        value = details.get("runtime")
        return int(value) if value else None
    values = [int(value) for value in details.get("episode_run_time") or [] if value]
    return round(sum(values) / len(values)) if values else None


def _search_result(payload: dict[str, Any], media_type: MediaType) -> MediaSearchResult:
    collection = payload.get("belongs_to_collection") or {}
    return MediaSearchResult(
        id=int(payload["id"]),
        media_type=media_type,
        title=_title(payload, media_type),
        original_title=_original_title(payload),
        year=_year_from_payload(payload, media_type),
        poster_url=image_url(payload.get("poster_path")),
        overview=payload.get("overview"),
        collection_id=int(collection["id"]) if collection.get("id") else None,
    )


def _parse_multi_search(payload: dict[str, Any]) -> list[MediaSearchResult]:
    results: list[MediaSearchResult] = []
    for item in payload.get("results") or []:
        media_type = item.get("media_type")
        if media_type not in (MediaType.MOVIE, MediaType.TV):
            continue
        results.append(_search_result(item, MediaType(media_type)))
    return results


def _parse_collection_search(payload: dict[str, Any]) -> list[MediaSearchResult]:
    results: list[MediaSearchResult] = []
    for item in payload.get("results") or []:
        if not item.get("id"):
            continue
        results.append(
            MediaSearchResult(
                id=int(item["id"]),
                media_type=MediaType.COLLECTION,
                title=str(item.get("name") or "Saga sans titre"),
                original_title=(
                    str(item["original_name"]) if item.get("original_name") else None
                ),
                year=None,
                poster_url=image_url(item.get("poster_path")),
                overview=item.get("overview"),
            )
        )
    return results


def _details(payload: dict[str, Any], media_type: MediaType) -> MediaDetails:
    genres = tuple(
        str(genre["name"])
        for genre in payload.get("genres") or []
        if genre.get("name")
    )
    collection = payload.get("belongs_to_collection") or {}
    return MediaDetails(
        id=int(payload["id"]),
        media_type=media_type,
        title=_title(payload, media_type),
        original_title=_original_title(payload),
        overview=payload.get("overview"),
        year=_year_from_payload(payload, media_type),
        runtime_minutes=_runtime(payload, media_type),
        poster_url=image_url(payload.get("poster_path")),
        backdrop_url=image_url(payload.get("backdrop_path")),
        genres=genres,
        rating=float(payload["vote_average"]) if payload.get("vote_average") is not None else None,
        collection_id=int(collection["id"]) if collection.get("id") else None,
        collection_name=str(collection["name"]) if collection.get("name") else None,
        number_of_seasons=(
            int(payload["number_of_seasons"])
            if payload.get("number_of_seasons") is not None
            else None
        ),
        number_of_episodes=(
            int(payload["number_of_episodes"])
            if payload.get("number_of_episodes") is not None
            else None
        ),
        tmdb_url=f"https://www.themoviedb.org/{media_type}/{int(payload['id'])}",
    )


def _collection(payload: dict[str, Any]) -> CollectionDetails:
    parts = tuple(
        _search_result(part, MediaType.MOVIE)
        for part in payload.get("parts") or []
        if part.get("id")
    )
    return CollectionDetails(
        id=int(payload["id"]),
        name=str(payload.get("name") or ""),
        overview=payload.get("overview"),
        poster_url=image_url(payload.get("poster_path")),
        parts=parts,
        tmdb_url=f"https://www.themoviedb.org/collection/{int(payload['id'])}",
    )


def _season(payload: dict[str, Any], series_id: int, season_number: int) -> SeasonDetails:
    episodes = tuple(
        Episode(
            id=int(item["id"]),
            episode_number=int(item.get("episode_number") or 0),
            name=str(item.get("name") or f"Épisode {item.get('episode_number') or 0}"),
            overview=item.get("overview"),
            runtime_minutes=int(item["runtime"]) if item.get("runtime") else None,
            air_date=item.get("air_date"),
            still_url=image_url(item.get("still_path")),
        )
        for item in payload.get("episodes") or []
        if item.get("id")
    )
    return SeasonDetails(
        series_id=series_id,
        season_number=season_number,
        name=str(payload.get("name") or f"Saison {season_number}"),
        overview=payload.get("overview"),
        poster_url=image_url(payload.get("poster_path")),
        episodes=episodes,
    )


def _providers(payload: dict[str, Any], region: str) -> list[WatchProvider]:
    country = payload.get("results", {}).get(region.upper()) or {}
    providers: list[WatchProvider] = []
    seen: set[tuple[int, str]] = set()

    for category, label in WATCH_CATEGORY_LABELS.items():
        for provider in country.get(category) or []:
            provider_id = provider.get("provider_id")
            link = country.get("link")
            if not provider_id or not link:
                continue
            key = (int(provider_id), str(link))
            if key in seen:
                continue
            seen.add(key)
            providers.append(
                WatchProvider(
                    provider_id=int(provider_id),
                    provider_name=str(provider.get("provider_name") or "Service"),
                    category=label,
                    link=str(link),
                    logo_url=image_url(provider.get("logo_path")),
                )
            )
    return providers


class TMDBProvider:
    name = "TMDB"

    def __init__(self, access_token: str, language: str = "fr-BE", region: str = "BE") -> None:
        if not access_token:
            raise ValueError("TMDB access token is required")
        self._access_token = access_token
        self.language = language
        self.region = region.upper()

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._access_token}",
            "accept": "application/json",
        }

    async def _get(
        self,
        http: aiohttp.ClientSession,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        try:
            payload = await fetch_json(
                http,
                f"{TMDB_API_URL}{path}",
                params=params,
                headers=self.headers,
            )
        except ProviderError as error:
            raise UserFacingError(
                "TMDB est momentanément indisponible. Réessaie dans un instant."
            ) from error
        if not isinstance(payload, dict):
            raise ProviderError("Unexpected TMDB payload")
        return payload

    async def search(
        self,
        http: aiohttp.ClientSession,
        query: str,
    ) -> list[MediaSearchResult]:
        query = query.strip()
        if not query:
            return []
        common = {
            "query": query,
            "language": self.language,
            "include_adult": "false",
            "page": "1",
        }
        multi_payload, collection_payload = await asyncio.gather(
            self._get(http, "/search/multi", {**common, "region": self.region}),
            self._get(http, "/search/collection", common),
        )
        return (_parse_multi_search(multi_payload) + _parse_collection_search(collection_payload))[:25]

    async def details(
        self,
        http: aiohttp.ClientSession,
        media_type: MediaType,
        media_id: int,
    ) -> MediaDetails:
        if media_type not in (MediaType.MOVIE, MediaType.TV):
            raise ValueError(f"Unsupported media type: {media_type}")
        payload = await self._get(
            http,
            f"/{media_type.value}/{media_id}",
            {"language": self.language},
        )
        return _details(payload, media_type)

    async def collection(
        self,
        http: aiohttp.ClientSession,
        collection_id: int,
    ) -> CollectionDetails:
        payload = await self._get(
            http,
            f"/collection/{collection_id}",
            {"language": self.language},
        )
        return _collection(payload)

    async def season(
        self,
        http: aiohttp.ClientSession,
        series_id: int,
        season_number: int,
    ) -> SeasonDetails:
        payload = await self._get(
            http,
            f"/tv/{series_id}/season/{season_number}",
            {"language": self.language},
        )
        return _season(payload, series_id, season_number)

    async def providers(
        self,
        http: aiohttp.ClientSession,
        media_type: MediaType,
        media_id: int,
    ) -> list[WatchProvider]:
        if media_type not in (MediaType.MOVIE, MediaType.TV):
            return []
        payload = await self._get(
            http,
            f"/{media_type.value}/{media_id}/watch/providers",
        )
        return _providers(payload, self.region)
