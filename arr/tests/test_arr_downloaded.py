from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr


class TestRadarrDownloaded:
    @pytest.fixture
    def radarr(self) -> Radarr:
        with patch("wi1_bot.arr.radarr.RadarrClient"):
            return Radarr("http://localhost:7878", "fake-api-key")

    def test_returns_only_movies_with_files(self, radarr: Radarr) -> None:
        radarr._radarr.movie.get = MagicMock(
            return_value=[
                {"tmdbId": 1, "hasFile": True},
                {"tmdbId": 2, "hasFile": False},
                {"tmdbId": 3, "hasFile": True},
            ]
        )

        assert radarr.downloaded_movie_tmdb_ids() == {1, 3}

    def test_empty_library(self, radarr: Radarr) -> None:
        radarr._radarr.movie.get = MagicMock(return_value=[])

        assert radarr.downloaded_movie_tmdb_ids() == set()


class TestSonarrDownloaded:
    @pytest.fixture
    def sonarr(self) -> Sonarr:
        with patch("wi1_bot.arr.sonarr.SonarrClient"):
            return Sonarr("http://localhost:8989", "fake-api-key")

    def test_returns_only_series_with_episode_files(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.series.get = MagicMock(
            return_value=[
                {"tvdbId": 10, "statistics": {"episodeFileCount": 5}},
                {"tvdbId": 20, "statistics": {"episodeFileCount": 0}},
                {"tvdbId": 30, "statistics": {}},  # never scanned / no stats
            ]
        )

        assert sonarr.downloaded_series_tvdb_ids() == {10}

    def test_empty_library(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.series.get = MagicMock(return_value=[])

        assert sonarr.downloaded_series_tvdb_ids() == set()
