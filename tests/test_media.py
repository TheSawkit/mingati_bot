import aiohttp
import pytest

from mingati.errors import UserFacingError
from mingati.providers.media.tmdb import (
    MediaType,
    _parse_collection,
    _parse_details,
    _parse_providers,
    _parse_search,
    _parse_season,
)
from mingati.services.media import MediaService


def test_parse_search_keeps_movies_and_tv() -> None:
    results = _parse_search(
        {
            "results": [
                {
                    "id": 1,
                    "media_type": "movie",
                    "title": "Dune",
                    "release_date": "2021-10-22",
                    "poster_path": "/dune.jpg",
                },
                {
                    "id": 2,
                    "media_type": "tv",
                    "name": "Dune",
                    "first_air_date": "2025-01-01",
                },
                {"id": 3, "media_type": "person", "name": "Frank Herbert"},
            ]
        }
    )

    assert [result.media_type for result in results] == [
        MediaType.MOVIE,
        MediaType.TV,
    ]
    assert results[0].poster_url.endswith("/dune.jpg")


def test_parse_movie_details() -> None:
    movie = _parse_details(
        {
            "id": 950,
            "title": "Ice Age",
            "original_title": "Ice Age",
            "overview": "A herd of animals...",
            "release_date": "2002-03-15",
            "runtime": 81,
            "vote_average": 7.4,
            "poster_path": "/poster.jpg",
            "backdrop_path": "/backdrop.jpg",
            "genres": [{"name": "Animation"}],
            "belongs_to_collection": {"id": 1, "name": "Ice Age Collection"},
        },
        MediaType.MOVIE,
    )

    assert movie.runtime_minutes == 81
    assert movie.collection_id == 1
    assert movie.year == 2002
    assert movie.poster_url == "https://image.tmdb.org/t/p/w500/poster.jpg"


def test_parse_collection_and_season() -> None:
    collection = _parse_collection(
        {
            "id": 1,
            "name": "Ice Age Collection",
            "overview": "Saga",
            "poster_path": "/poster.jpg",
            "parts": [
                {
                    "id": 950,
                    "title": "Ice Age",
                    "release_date": "2002-03-15",
                }
            ],
        }
    )
    season = _parse_season(
        {
            "name": "Season 1",
            "episodes": [
                {
                    "id": 10,
                    "episode_number": 2,
                    "name": "The Episode",
                    "runtime": 47,
                    "air_date": "2026-01-02",
                    "still_path": "/still.jpg",
                }
            ],
        },
        series_id=100,
        number=1,
    )

    assert collection.films[0].title == "Ice Age"
    assert season.episodes[0].number == 2
    assert season.episodes[0].runtime_minutes == 47


def test_parse_watch_providers_deduplicates() -> None:
    providers = _parse_providers(
        {
            "results": {
                "BE": {
                    "link": "https://www.themoviedb.org/movie/950/watch",
                    "flatrate": [
                        {"provider_id": 1, "provider_name": "Netflix"},
                    ],
                    "rent": [
                        {"provider_id": 1, "provider_name": "Netflix"},
                    ],
                }
            }
        },
        "BE",
    )

    assert len(providers) == 1
    assert providers[0].name == "Netflix"
    assert providers[0].category == "Streaming"


async def test_media_service_requires_tmdb() -> None:
    service = MediaService(None)

    import pytest

    with pytest.raises(UserFacingError, match="TMDB_API_TOKEN"):
        await service.search(None, "Dune")


async def test_tmdb_falls_back_to_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    from mingati.providers.media import tmdb

    calls = 0

    async def fake_fetch_json(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise aiohttp.ClientResponseError(None, (), status=401)
        return {"ok": True}

    monkeypatch.setattr(tmdb, "fetch_json", fake_fetch_json)

    provider = tmdb.TMDBProvider("test-credential")
    result = await provider._get(None, "/movie/1")

    assert result == {"ok": True}
    assert calls == 2


async def test_tmdb_rejects_invalid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    from mingati.providers.media import tmdb

    async def fake_fetch_json(*args, **kwargs):
        raise aiohttp.ClientResponseError(None, (), status=401)

    monkeypatch.setattr(tmdb, "fetch_json", fake_fetch_json)

    provider = tmdb.TMDBProvider("bad-credential")

    with pytest.raises(UserFacingError, match="clé TMDB est invalide"):
        await provider._get(None, "/movie/1")



class FakeProvider:
    def __init__(self, results, details=None, collection=None):
        self._results = results
        self._details = details
        self._collection = collection

    async def search(self, http, query):
        return self._results

    async def details(self, http, media_type, media_id):
        return self._details

    async def collection(self, http, collection_id):
        return self._collection


async def test_media_search_returns_exact_title_only() -> None:
    from mingati.providers.media.tmdb import MediaSearchResult

    results = [
        MediaSearchResult(1, MediaType.MOVIE, "Interstellar", "Interstellar", 2014, None),
        MediaSearchResult(2, MediaType.MOVIE, "Interstellar: Extended", None, 2015, None),
    ]
    service = MediaService(FakeProvider(results))

    found = await service.search(None, "Interstellar")

    assert found == [results[0]]


async def test_media_search_returns_detected_saga() -> None:
    from mingati.providers.media.tmdb import CollectionDetails, MediaDetails, MediaSearchResult

    results = [
        MediaSearchResult(
            1,
            MediaType.MOVIE,
            "Harry Potter à l'école des sorciers",
            "Harry Potter and the Philosopher's Stone",
            2001,
            None,
        ),
        MediaSearchResult(2, MediaType.MOVIE, "Autre résultat", None, 2002, None),
    ]
    details = MediaDetails(
        id=1,
        media_type=MediaType.MOVIE,
        title=results[0].title,
        original_title=results[0].original_title,
        overview=None,
        year=2001,
        runtime_minutes=152,
        poster_url=None,
        backdrop_url=None,
        genres=(),
        rating=7.9,
        collection_id=99,
        collection_name="Harry Potter - Saga",
        seasons=None,
        episodes=None,
        tmdb_url="https://www.themoviedb.org/movie/1",
    )
    collection = CollectionDetails(
        id=99,
        name="Harry Potter - Saga",
        overview=None,
        poster_url=None,
        films=(results[0], results[1]),
        tmdb_url="https://www.themoviedb.org/collection/99",
    )
    service = MediaService(FakeProvider(results, details, collection))

    found = await service.search(None, "Harry Potter")

    assert found == list(collection.films)
