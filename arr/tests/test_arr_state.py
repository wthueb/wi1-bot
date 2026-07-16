from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.arr.common import MediaState
from wi1_bot.arr.movie import Movie
from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Series, Sonarr


class TestMovieState:
    @pytest.fixture
    def radarr(self) -> Radarr:
        with patch("wi1_bot.arr.radarr.RadarrClient"):
            return Radarr("http://localhost:7878", "fake-api-key")

    @pytest.fixture
    def base_json(self) -> dict[str, Any]:
        return {"title": "The Matrix", "year": 1999, "tmdbId": 603, "imdbId": "tt0133093"}

    def test_absent_when_not_in_library(self, radarr: Radarr, base_json: dict[str, Any]) -> None:
        # no library "id" -> ABSENT
        assert radarr.movie_state(Movie(base_json)) is MediaState.ABSENT

    def test_downloaded_when_movie_file_exists(
        self, radarr: Radarr, base_json: dict[str, Any]
    ) -> None:
        # lookup returns the library record itself, so movieFileId is read straight
        # off it (hasFile is only populated by the /movie controller, not lookup)
        movie = Movie({**base_json, "id": 1, "monitored": True, "movieFileId": 9})

        assert radarr.movie_state(movie) is MediaState.DOWNLOADED

    def test_monitored_when_in_library_without_files(
        self, radarr: Radarr, base_json: dict[str, Any]
    ) -> None:
        movie = Movie({**base_json, "id": 1, "monitored": True, "movieFileId": 0})

        assert radarr.movie_state(movie) is MediaState.MONITORED

    def test_absent_when_in_library_unmonitored_without_files(
        self, radarr: Radarr, base_json: dict[str, Any]
    ) -> None:
        movie = Movie({**base_json, "id": 1, "monitored": False, "movieFileId": 0})

        assert radarr.movie_state(movie) is MediaState.ABSENT

    def test_state_never_calls_api(self, radarr: Radarr, base_json: dict[str, Any]) -> None:
        # every state is derived from the lookup json alone
        radarr._radarr.movie.get = MagicMock()
        radarr._radarr.movie_file.get = MagicMock()

        for extra in ({}, {"id": 1, "monitored": True, "movieFileId": 9}):
            radarr.movie_state(Movie({**base_json, **extra}))

        radarr._radarr.movie.get.assert_not_called()  # ty: ignore[unresolved-attribute]
        radarr._radarr.movie_file.get.assert_not_called()  # ty: ignore[unresolved-attribute]


class TestSeriesState:
    @pytest.fixture
    def sonarr(self) -> Sonarr:
        with patch("wi1_bot.arr.sonarr.SonarrClient"):
            return Sonarr("http://localhost:8989", "fake-api-key")

    @pytest.fixture
    def base_json(self) -> dict[str, Any]:
        return {"title": "Burn Notice", "year": 2007, "tvdbId": 82064, "imdbId": "tt0810788"}

    @staticmethod
    def _series_detail(episode_file_count: int) -> dict[str, Any]:
        return {"id": 1, "statistics": {"episodeFileCount": episode_file_count}}

    def test_absent_when_not_in_library(self, sonarr: Sonarr, base_json: dict[str, Any]) -> None:
        # no library "id" -> db_id is None -> ABSENT without touching the API
        sonarr._sonarr.series.get = MagicMock()

        assert sonarr.series_state(Series(base_json)) is MediaState.ABSENT
        sonarr._sonarr.series.get.assert_not_called()  # ty: ignore[unresolved-attribute]

    def test_downloaded_when_episode_files_exist(
        self, sonarr: Sonarr, base_json: dict[str, Any]
    ) -> None:
        series = Series({**base_json, "id": 1, "monitored": True})
        sonarr._sonarr.series.get = MagicMock(return_value=self._series_detail(42))

        assert sonarr.series_state(series) is MediaState.DOWNLOADED
        get = sonarr._sonarr.series.get
        get.assert_called_once_with(item_id=1)  # ty: ignore[unresolved-attribute]

    def test_monitored_when_in_library_without_files(
        self, sonarr: Sonarr, base_json: dict[str, Any]
    ) -> None:
        series = Series({**base_json, "id": 1, "monitored": True})
        sonarr._sonarr.series.get = MagicMock(return_value=self._series_detail(0))

        assert sonarr.series_state(series) is MediaState.MONITORED

    def test_absent_when_in_library_unmonitored_without_files(
        self, sonarr: Sonarr, base_json: dict[str, Any]
    ) -> None:
        series = Series({**base_json, "id": 1, "monitored": False})
        sonarr._sonarr.series.get = MagicMock(return_value=self._series_detail(0))

        assert sonarr.series_state(series) is MediaState.ABSENT
