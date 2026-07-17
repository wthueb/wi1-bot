from dataclasses import dataclass
from typing import Any

import requests

from wi1_bot.bot.config import TmdbConfig

BASE_URL = "https://api.themoviedb.org/3"

MAX_CAST = 5


@dataclass
class Person:
    name: str
    tmdb_id: int
    imdb_id: str | None = None

    @property
    def url(self) -> str:
        # prefer imdb like Movie/Series do, falling back to the person's tmdb page
        if self.imdb_id:
            return f"https://imdb.com/name/{self.imdb_id}"

        return f"https://themoviedb.org/person/{self.tmdb_id}"

    def __str__(self) -> str:
        return f"[{self.name}]({self.url})"


@dataclass
class Credits:
    directors: list[Person]  # creators for a series
    cast: list[Person]


@dataclass
class SeriesDetails:
    credits: Credits
    rating: float | None  # tmdb community rating (vote_average), None if unrated


class Tmdb:
    @classmethod
    def from_config(cls, config: TmdbConfig | None) -> "Tmdb | None":
        """Build a client from config, or None if tmdb is unset or the api key is
        still the template placeholder — callers then skip TMDB entirely instead of
        logging failed queries."""
        if config is None or "XXX" in config.api_key:
            return None

        return cls(config.api_key)

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _get(self, path: str, **params: str) -> dict[str, Any]:
        resp = requests.get(
            f"{BASE_URL}{path}", params={"api_key": self._api_key, **params}, timeout=10
        )
        resp.raise_for_status()

        json = resp.json()
        assert isinstance(json, dict)
        return json

    def _person(self, json: dict[str, Any]) -> Person:
        """Build a Person, resolving their imdb id (one extra request); on failure the
        Person just keeps its tmdb fallback url."""
        person = Person(json["name"], json["id"])

        try:
            external_ids = self._get(f"/person/{person.tmdb_id}/external_ids")
        except requests.RequestException:
            return person

        person.imdb_id = external_ids.get("imdb_id") or None

        return person

    def movie_credits(self, tmdb_id: int) -> Credits:
        json = self._get(f"/movie/{tmdb_id}/credits")

        directors = [self._person(c) for c in json.get("crew", []) if c.get("job") == "Director"]
        cast = [self._person(c) for c in json.get("cast", [])[:MAX_CAST]]

        return Credits(directors=directors, cast=cast)

    def series_details(self, tvdb_id: int) -> SeriesDetails | None:
        """Look up a series' creators, cast and tmdb rating, or None if TMDB doesn't
        know the TVDB id."""
        found = self._get(f"/find/{tvdb_id}", external_source="tvdb_id")

        tv_results = found.get("tv_results", [])

        if not tv_results:
            return None

        tmdb_id: int = tv_results[0]["id"]

        json = self._get(f"/tv/{tmdb_id}", append_to_response="aggregate_credits")

        creators = [self._person(c) for c in json.get("created_by", [])]
        cast = [
            self._person(c) for c in json.get("aggregate_credits", {}).get("cast", [])[:MAX_CAST]
        ]

        # unrated shows report vote_average 0
        rating = json.get("vote_average") or None

        return SeriesDetails(credits=Credits(directors=creators, cast=cast), rating=rating)
