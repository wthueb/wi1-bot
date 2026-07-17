from typing import Any
from unittest.mock import MagicMock, patch

from wi1_bot.bot.config import TmdbConfig
from wi1_bot.bot.tmdb import Person, Tmdb


def _mock_response(json: dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.json.return_value = json
    return resp


def _fake_get(routes: dict[str, dict[str, Any]]) -> Any:
    """Return a requests.get stand-in that answers by url fragment; person
    external_ids requests get imdb id nm<tmdb_id> unless overridden."""

    def fake_get(url: str, params: dict[str, str], timeout: int) -> MagicMock:
        for fragment, json in routes.items():
            if fragment in url:
                return _mock_response(json)

        if "/external_ids" in url:
            person_id = url.split("/person/")[1].split("/")[0]
            return _mock_response({"imdb_id": f"nm{person_id}"})

        raise AssertionError(f"unexpected request: {url}")

    return fake_get


class TestFromConfig:
    def test_no_config_returns_none(self) -> None:
        assert Tmdb.from_config(None) is None

    def test_placeholder_key_returns_none(self) -> None:
        # unfilled template value: skip TMDB entirely instead of logging failed queries
        assert Tmdb.from_config(TmdbConfig(api_key="XXX")) is None

    def test_real_key_returns_client(self) -> None:
        assert isinstance(Tmdb.from_config(TmdbConfig(api_key="real-key")), Tmdb)


class TestPerson:
    def test_prefers_imdb_url(self) -> None:
        person = Person("Jane Director", 101, imdb_id="nm0000101")

        assert str(person) == "[Jane Director](https://imdb.com/name/nm0000101)"

    def test_falls_back_to_tmdb_url(self) -> None:
        person = Person("Jane Director", 101)

        assert str(person) == "[Jane Director](https://themoviedb.org/person/101)"


class TestMovieCredits:
    def test_extracts_directors_and_cast(self) -> None:
        credits_json = {
            "cast": [{"name": f"Actor {i}", "id": i} for i in range(10)],
            "crew": [
                {"name": "Some Editor", "job": "Editor", "id": 100},
                {"name": "Jane Director", "job": "Director", "id": 101},
            ],
        }

        with patch(
            "wi1_bot.bot.tmdb.requests.get",
            side_effect=_fake_get({"/movie/123/credits": credits_json}),
        ):
            credits = Tmdb("key").movie_credits(123)

        assert credits.directors == [Person("Jane Director", 101, imdb_id="nm101")]
        # cast is capped at 5
        assert credits.cast == [Person(f"Actor {i}", i, imdb_id=f"nm{i}") for i in range(5)]

    def test_missing_fields(self) -> None:
        with patch("wi1_bot.bot.tmdb.requests.get", return_value=_mock_response({})):
            credits = Tmdb("key").movie_credits(123)

        assert credits.directors == []
        assert credits.cast == []

    def test_no_imdb_id_keeps_tmdb_fallback(self) -> None:
        credits_json = {"cast": [{"name": "Obscure Actor", "id": 9}]}

        with patch(
            "wi1_bot.bot.tmdb.requests.get",
            side_effect=_fake_get(
                {"/movie/123/credits": credits_json, "/person/9/external_ids": {"imdb_id": None}}
            ),
        ):
            credits = Tmdb("key").movie_credits(123)

        assert credits.cast == [Person("Obscure Actor", 9, imdb_id=None)]
        assert "themoviedb.org/person/9" in credits.cast[0].url


class TestSeriesDetails:
    def test_resolves_tvdb_id_then_fetches_details(self) -> None:
        find_json = {"tv_results": [{"id": 456}]}
        tv_json = {
            "created_by": [{"name": "Show Creator", "id": 7}],
            "aggregate_credits": {"cast": [{"name": "Lead Actor", "id": 8}]},
            "vote_average": 8.7,
        }

        with patch(
            "wi1_bot.bot.tmdb.requests.get",
            side_effect=_fake_get({"/find/789": find_json, "/tv/456": tv_json}),
        ) as get:
            details = Tmdb("key").series_details(789)

        assert details is not None
        assert details.credits.directors == [Person("Show Creator", 7, imdb_id="nm7")]
        assert details.credits.cast == [Person("Lead Actor", 8, imdb_id="nm8")]
        assert details.rating == 8.7

        find_call = get.call_args_list[0]
        assert "/find/789" in find_call.args[0]
        assert find_call.kwargs["params"]["external_source"] == "tvdb_id"

    def test_unrated_series_has_no_rating(self) -> None:
        find_json = {"tv_results": [{"id": 456}]}
        tv_json = {"vote_average": 0.0}

        with patch(
            "wi1_bot.bot.tmdb.requests.get",
            side_effect=_fake_get({"/find/789": find_json, "/tv/456": tv_json}),
        ):
            details = Tmdb("key").series_details(789)

        assert details is not None
        assert details.rating is None

    def test_unknown_tvdb_id_returns_none(self) -> None:
        with patch(
            "wi1_bot.bot.tmdb.requests.get", return_value=_mock_response({"tv_results": []})
        ):
            assert Tmdb("key").series_details(789) is None
