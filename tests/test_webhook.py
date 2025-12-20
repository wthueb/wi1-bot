from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.webhook import on_download, on_grab


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

        # Create transcoding config mock
        transcoding = MagicMock()
        transcoding.profiles = {"good": profile}

        config.transcoding = transcoding
        return config

    @pytest.fixture
    def movie_download_request(self) -> dict[str, Any]:
        return {
            "eventType": "Download",
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
            "series": {
                "id": 1,
                "title": "Game of Thrones",
                "path": "/tv/Game of Thrones",
            },
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

    @patch("wi1_bot.webhook.push")
    def test_on_grab(self, mock_push: MagicMock, grab_request: dict[str, Any]) -> None:
        on_grab(grab_request)

        mock_push.send.assert_called_once_with(
            "The.Matrix.1999.1080p.BluRay.x265",
            title="file grabbed (qBittorrent)",
        )

    @patch("wi1_bot.webhook.radarr")
    @patch("wi1_bot.webhook.push")
    @patch("wi1_bot.webhook.queue")
    @patch("wi1_bot.webhook.config")
    def test_on_download_movie_without_transcoding(
        self,
        mock_config: MagicMock,
        mock_queue: MagicMock,
        mock_push: MagicMock,
        mock_radarr: MagicMock,
        movie_download_request: dict[str, Any],
    ) -> None:
        # Mock config with no transcoding
        mock_config.transcoding = None
        mock_radarr._radarr.get_movie = MagicMock(return_value={"qualityProfileId": 1})
        mock_radarr.get_quality_profile_name = MagicMock(return_value="good")

        on_download(movie_download_request)

        mock_push.send.assert_called_once_with(
            "The Matrix (1999).mkv", title="new movie downloaded"
        )
        mock_queue.add.assert_not_called()

    @patch("wi1_bot.webhook.radarr")
    @patch("wi1_bot.webhook.push")
    @patch("wi1_bot.webhook.queue")
    @patch("wi1_bot.webhook.config")
    @patch("wi1_bot.webhook.replace_remote_paths")
    def test_on_download_movie_with_transcoding(
        self,
        mock_replace_paths: MagicMock,
        mock_config: MagicMock,
        mock_queue: MagicMock,
        mock_push: MagicMock,
        mock_radarr: MagicMock,
        movie_download_request: dict[str, Any],
        mock_transcoding_config: MagicMock,
    ) -> None:
        # Use the fixture config with transcoding profiles
        mock_config.transcoding = mock_transcoding_config.transcoding
        mock_radarr._radarr.get_movie = MagicMock(return_value={"qualityProfileId": 1})
        mock_radarr.get_quality_profile_name = MagicMock(return_value="good")
        mock_replace_paths.return_value = Path("/movies/The Matrix (1999)/The Matrix (1999).mkv")

        on_download(movie_download_request)

        mock_push.send.assert_called_once_with(
            "The Matrix (1999).mkv", title="new movie downloaded"
        )
        mock_queue.add.assert_called_once_with(
            path="/movies/The Matrix (1999)/The Matrix (1999).mkv",
            languages="eng",
            video_params="-c:v libx265",
            audio_params="-c:a aac",
        )

    @patch("wi1_bot.webhook.sonarr")
    @patch("wi1_bot.webhook.push")
    @patch("wi1_bot.webhook.queue")
    @patch("wi1_bot.webhook.config")
    @patch("wi1_bot.webhook.replace_remote_paths")
    def test_on_download_series(
        self,
        mock_replace_paths: MagicMock,
        mock_config: MagicMock,
        mock_queue: MagicMock,
        mock_push: MagicMock,
        mock_sonarr: MagicMock,
        series_download_request: dict[str, Any],
        mock_transcoding_config: MagicMock,
    ) -> None:
        # Use the fixture config with transcoding profiles
        mock_config.transcoding = mock_transcoding_config.transcoding
        mock_sonarr._sonarr.get_series = MagicMock(return_value={"qualityProfileId": 1})
        mock_sonarr.get_quality_profile_name = MagicMock(return_value="good")
        mock_replace_paths.return_value = Path("/tv/Game of Thrones/Season 01/S01E01.mkv")

        on_download(series_download_request)

        mock_push.send.assert_called_once_with("S01E01.mkv", title="new episode downloaded")
        mock_queue.add.assert_called_once()

    @patch("wi1_bot.webhook.radarr")
    @patch("wi1_bot.webhook.push")
    @patch("wi1_bot.webhook.config")
    def test_on_download_upgrade_no_notification(
        self,
        mock_config: MagicMock,
        mock_push: MagicMock,
        mock_radarr: MagicMock,
        movie_download_request: dict[str, Any],
    ) -> None:
        movie_download_request["isUpgrade"] = True
        # Mock config with no transcoding
        mock_config.transcoding = None
        mock_radarr._radarr.get_movie = MagicMock(return_value={"qualityProfileId": 1})
        mock_radarr.get_quality_profile_name = MagicMock(return_value="good")

        on_download(movie_download_request)

        mock_push.send.assert_not_called()

    def test_on_download_unknown_request(self) -> None:
        unknown_request = {
            "eventType": "Download",
            "isUpgrade": False,
        }

        with pytest.raises(ValueError, match="unknown download request"):
            on_download(unknown_request)
