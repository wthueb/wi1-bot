from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.arr.common import ImportMode


class TestWebhook:
    @pytest.fixture
    def mock_transcoding_config(self) -> MagicMock:
        # Create a Pydantic-like mock config object with transcoding
        config = MagicMock()

        # Create transcoding profile mock
        profile = MagicMock()
        profile.languages = "eng"
        profile.video_params = "-c:v libx265"
        profile.audio_params = "-c:a aac"
        profile.keep_original_language = True

        # Create transcoding config mock
        transcoding = MagicMock()
        transcoding.profiles = {"good": profile}

        config.transcoding = transcoding
        return config

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

    @pytest.fixture
    def grab_request(self) -> dict[str, Any]:
        return {
            "eventType": "Grab",
            "release": {"releaseTitle": "The.Matrix.1999.1080p.BluRay.x265"},
            "downloadClient": "qBittorrent",
        }

    def test_on_download_movie_without_transcoding(
        self,
        radarr_instance: MagicMock,
        movie_download_request: dict[str, Any],
    ) -> None:
        from wi1_bot import webhook

        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1}
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.transcoding = None
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(webhook, "instances", [radarr_instance]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue") as mock_queue,
            patch.object(webhook, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr

            webhook.on_download(movie_download_request)

        mock_queue.add.assert_not_called()

    def test_on_download_movie_with_transcoding(
        self,
        radarr_instance: MagicMock,
        movie_download_request: dict[str, Any],
        mock_transcoding_config: MagicMock,
    ) -> None:
        from wi1_bot import webhook

        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {
            "qualityProfileId": 1,
            "originalLanguage": {"id": 1, "name": "English"},
        }
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.transcoding = mock_transcoding_config.transcoding
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(webhook, "instances", [radarr_instance]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue") as mock_queue,
            patch.object(webhook, "Radarr") as mock_radarr_cls,
            patch.object(webhook, "replace_remote_paths") as mock_replace_paths,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            mock_replace_paths.return_value = Path(
                "/movies/The Matrix (1999)/The Matrix (1999).mkv"
            )

            webhook.on_download(movie_download_request)

        mock_queue.add.assert_called_once_with(
            path="/movies/The Matrix (1999)/The Matrix (1999).mkv",
            languages="eng",
            video_params="-c:v libx265",
            audio_params="-c:a aac",
        )

    def test_on_download_movie_keeps_original_language(
        self,
        radarr_instance: MagicMock,
        movie_download_request: dict[str, Any],
        mock_transcoding_config: MagicMock,
    ) -> None:
        from wi1_bot import webhook

        mock_radarr = MagicMock()
        # a Japanese title whose original audio/subs must survive the "eng" keep-list
        mock_radarr.get_movie_by_id.return_value = {
            "qualityProfileId": 1,
            "originalLanguage": {"id": 8, "name": "Japanese"},
        }
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.transcoding = mock_transcoding_config.transcoding
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(webhook, "instances", [radarr_instance]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue") as mock_queue,
            patch.object(webhook, "Radarr") as mock_radarr_cls,
            patch.object(webhook, "replace_remote_paths") as mock_replace_paths,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            mock_replace_paths.return_value = Path(
                "/movies/The Matrix (1999)/The Matrix (1999).mkv"
            )

            webhook.on_download(movie_download_request)

        mock_queue.add.assert_called_once_with(
            path="/movies/The Matrix (1999)/The Matrix (1999).mkv",
            languages="eng,jpn",
            video_params="-c:v libx265",
            audio_params="-c:a aac",
        )

    def test_on_download_movie_keep_original_language_disabled(
        self,
        radarr_instance: MagicMock,
        movie_download_request: dict[str, Any],
        mock_transcoding_config: MagicMock,
    ) -> None:
        from wi1_bot import webhook

        # a Japanese title, but the profile opts out of keeping the original language
        mock_transcoding_config.transcoding.profiles["good"].keep_original_language = False

        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {
            "qualityProfileId": 1,
            "originalLanguage": {"id": 8, "name": "Japanese"},
        }
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.transcoding = mock_transcoding_config.transcoding
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(webhook, "instances", [radarr_instance]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue") as mock_queue,
            patch.object(webhook, "Radarr") as mock_radarr_cls,
            patch.object(webhook, "replace_remote_paths") as mock_replace_paths,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr
            mock_replace_paths.return_value = Path(
                "/movies/The Matrix (1999)/The Matrix (1999).mkv"
            )

            webhook.on_download(movie_download_request)

        mock_queue.add.assert_called_once_with(
            path="/movies/The Matrix (1999)/The Matrix (1999).mkv",
            languages="eng",
            video_params="-c:v libx265",
            audio_params="-c:a aac",
        )

    def test_on_download_series(
        self,
        sonarr_instance: MagicMock,
        series_download_request: dict[str, Any],
        mock_transcoding_config: MagicMock,
    ) -> None:
        from wi1_bot import webhook

        mock_sonarr = MagicMock()
        mock_sonarr.get_series_by_id.return_value = {"qualityProfileId": 1}
        mock_sonarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.transcoding = mock_transcoding_config.transcoding
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(webhook, "instances", [sonarr_instance]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue") as mock_queue,
            patch.object(webhook, "Sonarr") as mock_sonarr_cls,
            patch.object(webhook, "replace_remote_paths") as mock_replace_paths,
        ):
            mock_sonarr_cls.from_config.return_value = mock_sonarr
            mock_replace_paths.return_value = Path("/tv/Game of Thrones/Season 01/S01E01.mkv")

            webhook.on_download(series_download_request)

        mock_queue.add.assert_called_once()

    def test_on_download_upgrade_no_notification(
        self,
        radarr_instance: MagicMock,
        movie_download_request: dict[str, Any],
    ) -> None:
        from wi1_bot import webhook

        movie_download_request["isUpgrade"] = True

        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1}
        mock_radarr.get_quality_profile_name.return_value = "good"

        mock_config = MagicMock()
        mock_config.transcoding = None
        mock_config.radarr4k = None
        mock_config.sonarr4k = None

        with (
            patch.object(webhook, "instances", [radarr_instance]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr

            webhook.on_download(movie_download_request)

    def test_on_download_movie_triggers_4k_scan(
        self,
        movie_download_request: dict[str, Any],
    ) -> None:
        from wi1_bot import webhook

        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1, "tmdbId": 603}
        mock_radarr.get_quality_profile_name.return_value = "good"
        mock_radarr.is_movie_monitored.return_value = True

        mock_config = MagicMock()
        mock_config.transcoding = None
        mock_config.sonarr4k = None
        # the matched instance must be config.radarr itself for the 4k scan to fire
        mock_config.radarr.instance_name = "Radarr"

        with (
            patch.object(webhook, "instances", [mock_config.radarr]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue"),
            patch.object(webhook, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr

            webhook.on_download(movie_download_request)

        mock_radarr.is_movie_monitored.assert_called_once_with(603)
        mock_radarr.downloaded_movies_scan.assert_called_once_with(
            Path("/movies/The Matrix (1999)/The Matrix (1999).mkv"), import_mode=ImportMode.COPY
        )

    def test_on_download_movie_skips_4k_scan_when_not_monitored(
        self,
        movie_download_request: dict[str, Any],
    ) -> None:
        from wi1_bot import webhook

        mock_radarr = MagicMock()
        mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1, "tmdbId": 603}
        mock_radarr.get_quality_profile_name.return_value = "good"
        mock_radarr.is_movie_monitored.return_value = False

        mock_config = MagicMock()
        mock_config.transcoding = None
        mock_config.sonarr4k = None
        mock_config.radarr.instance_name = "Radarr"

        with (
            patch.object(webhook, "instances", [mock_config.radarr]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue"),
            patch.object(webhook, "Radarr") as mock_radarr_cls,
        ):
            mock_radarr_cls.from_config.return_value = mock_radarr

            webhook.on_download(movie_download_request)

        mock_radarr.downloaded_movies_scan.assert_not_called()

    def test_on_download_series_triggers_4k_scan(
        self,
        series_download_request: dict[str, Any],
    ) -> None:
        from wi1_bot import webhook

        mock_sonarr = MagicMock()
        mock_sonarr.get_series_by_id.return_value = {"qualityProfileId": 1, "tvdbId": 121361}
        mock_sonarr.get_quality_profile_name.return_value = "good"
        mock_sonarr.is_episode_monitored.return_value = True

        mock_config = MagicMock()
        mock_config.transcoding = None
        mock_config.radarr4k = None
        # the matched instance must be config.sonarr itself for the 4k scan to fire
        mock_config.sonarr.instance_name = "Sonarr"

        with (
            patch.object(webhook, "instances", [mock_config.sonarr]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue"),
            patch.object(webhook, "Sonarr") as mock_sonarr_cls,
        ):
            mock_sonarr_cls.from_config.return_value = mock_sonarr

            webhook.on_download(series_download_request)

        mock_sonarr.is_episode_monitored.assert_called_once_with(121361, 1, 1)
        mock_sonarr.downloaded_episodes_scan.assert_called_once_with(
            Path("/tv/Game of Thrones/Season 01/S01E01.mkv"), import_mode=ImportMode.COPY
        )

    def test_on_download_series_skips_4k_scan_when_not_monitored(
        self,
        series_download_request: dict[str, Any],
    ) -> None:
        from wi1_bot import webhook

        mock_sonarr = MagicMock()
        mock_sonarr.get_series_by_id.return_value = {"qualityProfileId": 1, "tvdbId": 121361}
        mock_sonarr.get_quality_profile_name.return_value = "good"
        mock_sonarr.is_episode_monitored.return_value = False

        mock_config = MagicMock()
        mock_config.transcoding = None
        mock_config.radarr4k = None
        mock_config.sonarr.instance_name = "Sonarr"

        with (
            patch.object(webhook, "instances", [mock_config.sonarr]),
            patch.object(webhook, "config", mock_config),
            patch.object(webhook, "queue"),
            patch.object(webhook, "Sonarr") as mock_sonarr_cls,
        ):
            mock_sonarr_cls.from_config.return_value = mock_sonarr

            webhook.on_download(series_download_request)

        mock_sonarr.downloaded_episodes_scan.assert_not_called()

    def test_on_download_unknown_instance(self) -> None:
        from wi1_bot import webhook

        request = {
            "eventType": "Download",
            "instanceName": "Nonexistent",
            "isUpgrade": False,
        }

        with patch.object(webhook, "instances", []):
            with pytest.raises(Exception, match="unknown instance"):
                webhook.on_download(request)

    def test_on_download_unknown_request(self, radarr_instance: MagicMock) -> None:
        from wi1_bot import webhook

        unknown_request = {
            "eventType": "Download",
            "instanceName": "Radarr",
            "isUpgrade": False,
        }

        with patch.object(webhook, "instances", [radarr_instance]):
            with pytest.raises(ValueError, match="unknown download request"):
                webhook.on_download(unknown_request)
