from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import aiohttp

from mingati.errors import UserFacingError
from mingati.providers.http import ProviderError, fetch_json

TMDB_API_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_URL = "https://image.tmdb.org/t/p/w500/"

WATCH_CATEGORIES = (
    ("flatrate", "Streaming"),
    ("free", "Gratuit"),
    ("ads", "Avec publicité"),
)


class MediaType(StrEnum):
    MOVIE = "movie"
    TV = "tv"


@dataclass(frozen=True, slots=True)
class MediaSearchResult:
    id: int
    media_type: MediaType
    title: str
    original_title: str | None
    year: int | None
    poster_url: str | None


@dataclass(frozen=True, slots=True)
class CollectionSearchResult:
    id: int
    name: str
    poster_url: str | None


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
    seasons: int | None
    episodes: int | None
    tmdb_url: str


@dataclass(frozen=True, slots=True)
class CollectionDetails:
    id: int
    name: str
    overview: str | None
    poster_url: str | None
    films: tuple[MediaSearchResult, ...]
    tmdb_url: str


@dataclass(frozen=True, slots=True)
class Episode:
    id: int
    number: int
    name: str
    overview: str | None
    runtime_minutes: int | None
    air_date: str | None
    still_url: str | None


@dataclass(frozen=True, slots=True)
class SeasonDetails:
    series_id: int
    number: int
    name: str
    overview: str | None
    poster_url: str | None
    episodes: tuple[Episode, ...]


@dataclass(frozen=True, slots=True)
class WatchProvider:
    provider_id: int
    name: str
    category: str
    link: str
    logo_url: str | None = None


def image_url(path: str | None) -> str | None:
    return f"{TMDB_IMAGE_URL}{path.lstrip('/')}" if path else None


def _year(value: str | None) -> int | None:
    try:
        return int(value[:4]) if value else None
    except ValueError:
        return None


def _title(data: dict[str, Any]) -> str:
    return str(data.get("title") or data.get("name") or "Titre inconnu")


def _original_title(data: dict[str, Any]) -> str | None:
    value = data.get("original_title") or data.get("original_name")
    return str(value) if value else None


def _date(data: dict[str, Any], media_type: MediaType) -> int | None:
    key = "release_date" if media_type == MediaType.MOVIE else "first_air_date"
    return _year(data.get(key))


def _search_result(data: dict[str, Any], media_type: MediaType) -> MediaSearchResult:
    return MediaSearchResult(
        id=int(data["id"]),
        media_type=media_type,
        title=_title(data),
        original_title=_original_title(data),
        year=_date(data, media_type),
        poster_url=image_url(data.get("poster_path")),
    )


def _parse_search(data: dict[str, Any]) -> list[MediaSearchResult]:
    results: list[MediaSearchResult] = []
    for item in data.get("results") or []:
        media_type = item.get("media_type")
        if media_type in (MediaType.MOVIE, MediaType.TV):
            results.append(_search_result(item, MediaType(media_type)))
    return results


def _parse_collection_search(data: dict[str, Any]) -> list[CollectionSearchResult]:
    return [
        CollectionSearchResult(
            id=int(item["id"]),
            name=str(item.get("name") or "Saga"),
            poster_url=image_url(item.get("poster_path")),
        )
        for item in data.get("results") or []
        if item.get("id")
    ]


def _runtime(data: dict[str, Any], media_type: MediaType) -> int | None:
    if media_type == MediaType.MOVIE:
        return int(data["runtime"]) if data.get("runtime") else None
    values = [int(value) for value in data.get("episode_run_time") or [] if value]
    return round(sum(values) / len(values)) if values else None


def _parse_details(data: dict[str, Any], media_type: MediaType) -> MediaDetails:
    collection = data.get("belongs_to_collection") or {}
    return MediaDetails(
        id=int(data["id"]),
        media_type=media_type,
        title=_title(data),
        original_title=_original_title(data),
        overview=data.get("overview"),
        year=_date(data, media_type),
        runtime_minutes=_runtime(data, media_type),
        poster_url=image_url(data.get("poster_path")),
        backdrop_url=image_url(data.get("backdrop_path")),
        genres=tuple(str(genre["name"]) for genre in data.get("genres") or [] if genre.get("name")),
        rating=float(data["vote_average"]) if data.get("vote_average") is not None else None,
        collection_id=int(collection["id"]) if collection.get("id") else None,
        collection_name=str(collection["name"]) if collection.get("name") else None,
        seasons=(
            int(data["number_of_seasons"]) if data.get("number_of_seasons") is not None else None
        ),
        episodes=(
            int(data["number_of_episodes"]) if data.get("number_of_episodes") is not None else None
        ),
        tmdb_url=f"https://www.themoviedb.org/{media_type.value}/{int(data['id'])}",
    )


def _parse_collection(data: dict[str, Any]) -> CollectionDetails:
    films = tuple(
        _search_result(item, MediaType.MOVIE) for item in data.get("parts") or [] if item.get("id")
    )
    return CollectionDetails(
        id=int(data["id"]),
        name=str(data.get("name") or "Saga"),
        overview=data.get("overview"),
        poster_url=image_url(data.get("poster_path")),
        films=films,
        tmdb_url=f"https://www.themoviedb.org/collection/{int(data['id'])}",
    )


def _parse_season(data: dict[str, Any], series_id: int, number: int) -> SeasonDetails:
    episodes = tuple(
        Episode(
            id=int(item["id"]),
            number=int(item.get("episode_number") or 0),
            name=str(item.get("name") or f"Épisode {item.get('episode_number') or 0}"),
            overview=item.get("overview"),
            runtime_minutes=int(item["runtime"]) if item.get("runtime") else None,
            air_date=item.get("air_date"),
            still_url=image_url(item.get("still_path")),
        )
        for item in data.get("episodes") or []
        if item.get("id")
    )
    return SeasonDetails(
        series_id=series_id,
        number=number,
        name=str(data.get("name") or f"Saison {number}"),
        overview=data.get("overview"),
        poster_url=image_url(data.get("poster_path")),
        episodes=episodes,
    )


def _parse_providers(data: dict[str, Any], region: str) -> list[WatchProvider]:
    country = (data.get("results") or {}).get(region.upper()) or {}
    providers: list[WatchProvider] = []
    seen: set[tuple[int, str]] = set()

    for category, label in WATCH_CATEGORIES:
        for item in country.get(category) or []:
            provider_id = item.get("provider_id")
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
                    name=str(item.get("provider_name") or "Service"),
                    category=label,
                    link=str(link),
                    logo_url=image_url(item.get("logo_path")),
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

    async def _get(
        self,
        http: aiohttp.ClientSession,
        path: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "accept": "application/json",
        }
        try:
            data = await fetch_json(
                http,
                f"{TMDB_API_URL}{path}",
                params=params,
                headers=headers,
            )
        except aiohttp.ClientResponseError as error:
            if error.status == 429:
                raise UserFacingError(
                    "TMDB a temporairement limité les requêtes. Réessaie dans un instant."
                ) from error
            if error.status != 401:
                raise UserFacingError(
                    "TMDB est momentanément indisponible. Réessaie dans un instant."
                ) from error

            # TMDB also accepts the v3 API key for v3 GET endpoints.
            # Falling back here keeps TMDB_API_TOKEN compatible with either credential type.
            fallback_params = dict(params or {})
            fallback_params["api_key"] = self._access_token
            try:
                data = await fetch_json(
                    http,
                    f"{TMDB_API_URL}{path}",
                    params=fallback_params,
                    headers={"accept": "application/json"},
                )
            except aiohttp.ClientResponseError as fallback_error:
                if fallback_error.status == 401:
                    raise UserFacingError(
                        "La clé TMDB est invalide. Utilise une API Read Access Token "
                        "ou une API Key TMDB valide dans TMDB_API_TOKEN."
                    ) from None
                raise UserFacingError(
                    "TMDB est momentanément indisponible. Réessaie dans un instant."
                ) from fallback_error
        except ProviderError as error:
            raise UserFacingError(
                "TMDB est momentanément indisponible. Réessaie dans un instant."
            ) from error
        if not isinstance(data, dict):
            raise ProviderError("Unexpected TMDB payload")
        return data

    async def search_collections(
        self,
        http: aiohttp.ClientSession,
        query: str,
    ) -> list[CollectionSearchResult]:
        data = await self._get(
            http,
            "/search/collection",
            {
                "query": query,
                "language": self.language,
                "page": "1",
            },
        )
        return _parse_collection_search(data)[:5]

    async def search(
        self,
        http: aiohttp.ClientSession,
        query: str,
    ) -> list[MediaSearchResult]:
        data = await self._get(
            http,
            "/search/multi",
            {
                "query": query,
                "language": self.language,
                "include_adult": "false",
                "page": "1",
            },
        )
        return _parse_search(data)[:25]

    async def details(
        self,
        http: aiohttp.ClientSession,
        media_type: MediaType,
        media_id: int,
    ) -> MediaDetails:
        data = await self._get(
            http,
            f"/{media_type.value}/{media_id}",
            {"language": self.language},
        )
        return _parse_details(data, media_type)

    async def collection(
        self,
        http: aiohttp.ClientSession,
        collection_id: int,
    ) -> CollectionDetails:
        data = await self._get(
            http,
            f"/collection/{collection_id}",
            {"language": self.language},
        )
        return _parse_collection(data)

    async def season(
        self,
        http: aiohttp.ClientSession,
        series_id: int,
        season_number: int,
    ) -> SeasonDetails:
        data = await self._get(
            http,
            f"/tv/{series_id}/season/{season_number}",
            {"language": self.language},
        )
        return _parse_season(data, series_id, season_number)

    async def providers(
        self,
        http: aiohttp.ClientSession,
        media_type: MediaType,
        media_id: int,
    ) -> list[WatchProvider]:
        data = await self._get(
            http,
            f"/{media_type.value}/{media_id}/watch/providers",
        )
        return _parse_providers(data, self.region)
