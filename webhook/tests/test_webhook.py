from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import wi1_bot.webhook.app as app_mod
from wi1_bot.arr.common import ImportMode


class TestOnDownload:
    @pytest.fixture
    def radarr_instance(self) -> MagicMock:
        instance = MagicMock()
        instance.instance_name = "Radarr"
        return instance

    @pytest.fixture
    def sonarr_instance(self) -> MagicMock:
        instance = MagicMock()
        instance.instance_name = "Sonarr"
        return instance

    @pytest.fixture
    def movie_download_request(self) -> dict[str, Any]:
        return {
            "eventType": "Download",
            "instanceName": "Radarr",
            "movie": {
                "id": 1,
                "title": "The Matrix",
                "folderPath": "/movies/The Matrix (1999)",
            },
            "movieFile": {"relativePath": "The Matrix (1999).mkv"},
            "isUpgrade": False,
            "downloadClient": "qBittorrent",
        }

    @pytest.fixture
    def series_download_request(self) -> dict[str, Any]:
        return {
            "eventType": "Download",
            "instanceName": "Sonarr",
            "series": {
                "id": 1,
                "title": "Game of Thrones",
                "path": "/tv/Game of Thrones",
            },
            "episodes": [{"seasonNumber": 1, "episodeNumber": 1}],
            "episodeFile": {"relativePath": "Season 01/S01E01.mkv"},
            "isUpgrade": False,
            "downloadClient": "qBittorrent",
        }

    def test_movie_enqueues_arr_native_path(
        self, radarr_instance: MagicMock, movie_download_request: dict[str, Any]
    ) -> None:
        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {
            "qualityProfileId": 1,
            "originalLanguage": {"id": 1, "name": "English"},
        }
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(app_mod, "instances", [radarr_instance]),
            patch.object(app_mod, "config", mock_config),
            patch.object(app_mod, "queue") as mock_queue,
            patch.object(app_mod, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            app_mod.on_download(movie_download_request)

        # every completed download is enqueued, with the Arr-native path (no remote mapping)
        mock_queue.add.assert_called_once_with(
            path="/movies/The Matrix (1999)/The Matrix (1999).mkv",
            quality_profile="good",
            original_language="English",
        )

    def test_movie_passes_original_language(
        self, radarr_instance: MagicMock, movie_download_request: dict[str, Any]
    ) -> None:
        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {
            "qualityProfileId": 1,
            "originalLanguage": {"id": 8, "name": "Japanese"},
        }
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(app_mod, "instances", [radarr_instance]),
            patch.object(app_mod, "config", mock_config),
            patch.object(app_mod, "queue") as mock_queue,
            patch.object(app_mod, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            app_mod.on_download(movie_download_request)

        assert mock_queue.add.call_args.kwargs["original_language"] == "Japanese"

    def test_series_enqueues(
        self, sonarr_instance: MagicMock, series_download_request: dict[str, Any]
    ) -> None:
        mock_sonarr = MagicMock()
        mock_sonarr.get_series_by_id.return_value = {"qualityProfileId": 1}
        mock_sonarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(app_mod, "instances", [sonarr_instance]),
            patch.object(app_mod, "config", mock_config),
            patch.object(app_mod, "queue") as mock_queue,
            patch.object(app_mod, "Sonarr") as mock_sonarr_cls,
        ):
            mock_sonarr_cls.from_config.return_value = mock_sonarr
            app_mod.on_download(series_download_request)

        mock_queue.add.assert_called_once_with(
            path="/tv/Game of Thrones/Season 01/S01E01.mkv",
            quality_profile="good",
            original_language=None,
        )

    def test_movie_triggers_4k_scan(self, movie_download_request: dict[str, Any]) -> None:
        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1, "tmdbId": 603}
        mock_radarr.get_quality_profile_name.return_value = "good"
        mock_radarr.is_movie_monitored.return_value = True

        mock_config = MagicMock()
        mock_config.sonarr4k = None
        # the matched instance must be config.radarr itself for the 4k scan to fire
        mock_config.radarr.instance_name = "Radarr"

        with (
            patch.object(app_mod, "instances", [mock_config.radarr]),
            patch.object(app_mod, "config", mock_config),
            patch.object(app_mod, "queue"),
            patch.object(app_mod, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            app_mod.on_download(movie_download_request)

        mock_radarr.is_movie_monitored.assert_called_once_with(603)
        mock_radarr.downloaded_movies_scan.assert_called_once_with(
            Path("/movies/The Matrix (1999)/The Matrix (1999).mkv"), import_mode=ImportMode.COPY
        )

    def test_movie_skips_4k_scan_when_not_monitored(
        self, movie_download_request: dict[str, Any]
    ) -> None:
        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1, "tmdbId": 603}
        mock_radarr.get_quality_profile_name.return_value = "good"
        mock_radarr.is_movie_monitored.return_value = False

        mock_config = MagicMock()
        mock_config.sonarr4k = None
        mock_config.radarr.instance_name = "Radarr"

        with (
            patch.object(app_mod, "instances", [mock_config.radarr]),
            patch.object(app_mod, "config", mock_config),
            patch.object(app_mod, "queue"),
            patch.object(app_mod, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            app_mod.on_download(movie_download_request)

        mock_radarr.downloaded_movies_scan.assert_not_called()

    def test_series_triggers_4k_scan(self, series_download_request: dict[str, Any]) -> None:
        mock_sonarr = MagicMock()
        mock_sonarr.get_series_by_id.return_value = {"qualityProfileId": 1, "tvdbId": 121361}
        mock_sonarr.get_quality_profile_name.return_value = "good"
        mock_sonarr.is_episode_monitored.return_value = True

        mock_config = MagicMock()
        mock_config.radarr4k = None
        mock_config.sonarr.instance_name = "Sonarr"

        with (
            patch.object(app_mod, "instances", [mock_config.sonarr]),
            patch.object(app_mod, "config", mock_config),
            patch.object(app_mod, "queue"),
            patch.object(app_mod, "Sonarr") as mock_sonarr_cls,
        ):
            mock_sonarr_cls.from_config.return_value = mock_sonarr
            app_mod.on_download(series_download_request)

        mock_sonarr.is_episode_monitored.assert_called_once_with(121361, 1, 1)
        mock_sonarr.downloaded_episodes_scan.assert_called_once_with(
            Path("/tv/Game of Thrones/Season 01/S01E01.mkv"), import_mode=ImportMode.COPY
        )

    def test_unknown_instance(self) -> None:
        request = {"eventType": "Download", "instanceName": "Nonexistent", "isUpgrade": False}

        with patch.object(app_mod, "instances", []):
            with pytest.raises(Exception, match="unknown instance"):
                app_mod.on_download(request)

    def test_unknown_request(self, radarr_instance: MagicMock) -> None:
        unknown_request = {"eventType": "Download", "instanceName": "Radarr", "isUpgrade": False}

        with patch.object(app_mod, "instances", [radarr_instance]):
            with pytest.raises(ValueError, match="unknown download request"):
                app_mod.on_download(unknown_request)
