import json
from unittest.mock import patch

import pytest
import requests
from flask.testing import FlaskClient

import wi1_bot.webhook.imdb_popular as imdb_mod
from wi1_bot.webhook.app import app
from wi1_bot.webhook.config import IMDbPopularListConfig


@pytest.fixture
def client() -> FlaskClient:
    return app.test_client()


@pytest.fixture
def feed() -> list[dict[str, object]]:
    return [
        {"TmdbId": 238, "OriginalLanguage": "en", "Title": "The Godfather"},
        {"TmdbId": 550, "OriginalLanguage": "en", "Title": "Fight Club"},
        {"TmdbId": 603, "OriginalLanguage": "ja", "Title": "Example"},
        {"TmdbId": 238, "OriginalLanguage": "en", "Title": "The Godfather"},
        {"TmdbId": 680, "OriginalLanguage": "fr", "Title": "Example"},
    ]


@pytest.mark.parametrize(
    ("filters", "expected_ids"),
    [
        (IMDbPopularListConfig(), [238, 550, 603, 680]),
        (IMDbPopularListConfig(include_languages=["en", "ja"]), [238, 550, 603]),
        (IMDbPopularListConfig(exclude_languages=["en"]), [603, 680]),
        (
            IMDbPopularListConfig(include_languages=["en", "ja"], exclude_languages=["fr"]),
            [238, 550, 603],
        ),
        (IMDbPopularListConfig(include_languages=["de"]), []),
    ],
)
def test_imdb_popular_list_filters_original_language(
    client: FlaskClient,
    feed: list[dict[str, object]],
    filters: IMDbPopularListConfig,
    expected_ids: list[int],
) -> None:
    with (
        patch.object(imdb_mod.config.webhook, "imdb_popular_list", filters),
        patch.object(imdb_mod.requests, "get") as get,
    ):
        get.return_value.json.return_value = feed
        response = client.get("/lists/imdb/popular")

    assert response.status_code == 200
    assert response.get_json() == [{"id": movie_id} for movie_id in expected_ids]
    get.assert_called_once_with("https://api.radarr.video/v1/list/imdb/popular", timeout=10)


@pytest.mark.parametrize(
    "invalid_feed",
    [
        {"results": [{"TmdbId": 238, "OriginalLanguage": "en"}]},
        [{"TmdbId": 238, "OriginalLanguage": "en"}, {"TmdbId": 0, "OriginalLanguage": "fr"}],
        [{"TmdbId": True, "OriginalLanguage": "en"}],
        [{"TmdbId": 238}],
        [{"TmdbId": 238, "OriginalLanguage": "english"}],
    ],
)
def test_imdb_popular_list_rejects_malformed_feed_without_partial_success(
    client: FlaskClient, invalid_feed: object
) -> None:
    with patch.object(imdb_mod.requests, "get") as get:
        get.return_value.json.return_value = invalid_feed
        response = client.get("/lists/imdb/popular")

    assert response.status_code == 502
    assert response.get_json() == {"error": "IMDb popular list unavailable"}


@pytest.mark.parametrize(
    "failure", [requests.Timeout("timed out"), requests.HTTPError("bad status")]
)
def test_imdb_popular_list_rejects_upstream_failure(
    client: FlaskClient, failure: requests.RequestException
) -> None:
    with patch.object(imdb_mod.requests, "get") as get:
        if isinstance(failure, requests.HTTPError):
            get.return_value.raise_for_status.side_effect = failure
        else:
            get.side_effect = failure
        response = client.get("/lists/imdb/popular")

    assert response.status_code == 502
    assert response.get_json() == {"error": "IMDb popular list unavailable"}


def test_imdb_popular_list_rejects_invalid_json(client: FlaskClient) -> None:
    with patch.object(imdb_mod.requests, "get") as get:
        get.return_value.json.side_effect = json.JSONDecodeError("invalid JSON", "{", 0)
        response = client.get("/lists/imdb/popular")

    assert response.status_code == 502
    assert response.get_json() == {"error": "IMDb popular list unavailable"}
