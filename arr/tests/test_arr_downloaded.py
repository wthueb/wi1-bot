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


class TestSonarrDownloadedEpisodes:
    @pytest.fixture
    def sonarr(self) -> Sonarr:
        with patch("wi1_bot.arr.sonarr.SonarrClient"):
            return Sonarr("http://localhost:8989", "fake-api-key")

    def test_lists_episodes_with_files(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.series.get = MagicMock(
            return_value=[
                {
                    "id": 1,
                    "tvdbId": 10,
                    "title": "Show",
                    "imdbId": "tt1",
                    "statistics": {"episodeFileCount": 1},
                },
                {"id": 2, "tvdbId": 20, "title": "Empty", "statistics": {"episodeFileCount": 0}},
                {"id": 3, "tvdbId": 99, "title": "Unwatched", "statistics": {}},
            ]
        )
        sonarr._sonarr.episode.get = MagicMock(
            return_value=[
                {
                    "id": 101,
                    "seasonNumber": 1,
                    "episodeNumber": 1,
                    "title": "Pilot",
                    "airDate": "2026-01-01",
                    "hasFile": True,
                },
                {
                    "id": 102,
                    "seasonNumber": 1,
                    "episodeNumber": 2,
                    "title": "Next",
                    "hasFile": False,
                },
            ]
        )

        result = sonarr.downloaded_episodes_by_tvdb_id({10, 20})

        # 99 was not requested: absent; 20 has no files: empty without an episode fetch
        assert set(result) == {10, 20}
        assert result[20] == []
        sonarr._sonarr.episode.get.assert_called_once_with(series_id=1)

        (ep,) = result[10]
        assert ep.db_id == 101
        assert ep.full_title == "Show S01E01 - Pilot"

    def test_show_not_in_library_is_absent(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.series.get = MagicMock(return_value=[])

        assert sonarr.downloaded_episodes_by_tvdb_id({10}) == {}

    def test_no_requested_ids_skips_fetch(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.series.get = MagicMock()

        assert sonarr.downloaded_episodes_by_tvdb_id(set()) == {}
        sonarr._sonarr.series.get.assert_not_called()
