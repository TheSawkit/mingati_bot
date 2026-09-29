from mingati.errors import UserFacingError
from mingati.providers.media.tmdb import (
    MediaType,
    _collection,
    _details,
    _parse_collection_search,
    _parse_multi_search,
    _providers,
    _season,
)
from mingati.services.media import MediaService


def test_parse_multi_search_filters_people() -> None:
    payload = {
        "results": [
            {"id": 1, "media_type": "movie", "title": "Dune", "release_date": "2021-10-22"},
            {"id": 2, "media_type": "tv", "name": "Dune", "first_air_date": "2025-01-01"},
            {"id": 3, "media_type": "person", "name": "Frank Herbert"},
        ]
    }

    results = _parse_multi_search(payload)

    assert [result.media_type for result in results] == [MediaType.MOVIE, MediaType.TV]
    assert [result.year for result in results] == [2021, 2025]


def test_parse_collection_search() -> None:
    results = _parse_collection_search(
        {
            "results": [
                {
                    "id": 10,
                    "name": "Dune Collection",
                    "original_name": "Dune Collection",
                    "poster_path": "/dune.jpg",
                }
            ]
        }
    )

    assert results[0].media_type == MediaType.COLLECTION
    assert results[0].title == "Dune Collection"


def test_parse_movie_details_and_collection() -> None:
    movie = _details(
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
    collection = _collection(
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
                    "media_type": "movie",
                }
            ],
        }
    )

    assert movie.runtime_minutes == 81
    assert movie.collection_id == 1
    assert movie.year == 2002
    assert movie.poster_url == "https://image.tmdb.org/t/p/w500/poster.jpg"
    assert collection.parts[0].title == "Ice Age"


def test_parse_tv_season() -> None:
    season = _season(
        {
            "name": "Season 1",
            "overview": "Overview",
            "poster_path": "/season.jpg",
            "episodes": [
                {
                    "id": 10,
                    "episode_number": 2,
                    "name": "The Episode",
                    "overview": "Episode overview",
                    "runtime": 47,
                    "air_date": "2026-01-02",
                    "still_path": "/still.jpg",
                }
            ],
        },
        series_id=100,
        season_number=1,
    )

    assert season.episodes[0].episode_number == 2
    assert season.episodes[0].runtime_minutes == 47


def test_parse_watch_providers_deduplicates_same_provider_link() -> None:
    payload = {
        "results": {
            "BE": {
                "link": "https://www.themoviedb.org/movie/950/watch",
                "flatrate": [
                    {"provider_id": 1, "provider_name": "Netflix", "logo_path": "/netflix.png"}
                ],
                "rent": [
                    {"provider_id": 1, "provider_name": "Netflix", "logo_path": "/netflix.png"}
                ],
            }
        }
    }

    providers = _providers(payload, "BE")

    assert len(providers) == 1
    assert providers[0].provider_name == "Netflix"
    assert providers[0].category == "Streaming"


async def test_media_service_requires_tmdb() -> None:
    service = MediaService(None)

    import pytest

    with pytest.raises(UserFacingError, match="TMDB_API_TOKEN"):
        await service.search(None, "Dune")
