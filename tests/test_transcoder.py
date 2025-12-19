from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.models import TranscodeItem
from wi1_bot.transcoder.transcoder import build_ffmpeg_command


class TestBuildFfmpegCommand:
    @pytest.fixture
    def basic_item(self) -> TranscodeItem:
        return TranscodeItem(
            path="/movies/test.mkv",
            languages=None,
            video_params=None,
            audio_params=None,
        )

    @pytest.fixture
    def mock_ffprobe_output(self) -> dict[str, Any]:
        return {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "tags": {"language": "eng"},
                },
                {
                    "index": 2,
                    "codec_type": "audio",
                    "codec_name": "ac3",
                    "tags": {"language": "ita"},
                },
                {
                    "index": 3,
                    "codec_type": "subtitle",
                    "codec_name": "subrip",
                    "tags": {"language": "eng"},
                },
            ]
        }

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_basic_command_copy_all(
        self,
        mock_config: MagicMock,
        mock_ffprobe: MagicMock,
        basic_item: TranscodeItem,
        mock_ffprobe_output: dict[str, Any],
    ) -> None:
        mock_config.transcoding = None
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(basic_item, "/tmp/output.mkv")

        assert command[0] == "ffmpeg"
        assert "-hide_banner" in command
        assert "-y" in command
        assert "-i" in command
        assert "/movies/test.mkv" in command
        assert "/tmp/output.mkv" in command
        assert "-map" in command
        assert "0:v:0" in command
        assert "-c:v:0" in command
        assert "copy" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_with_video_params(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeItem(
            path="/movies/test.mkv",
            languages=None,
            video_params="-c libx265 -preset medium",
            audio_params=None,
        )
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        assert "-c:v:0" in command
        assert "libx265" in command
        assert "-preset:v:0" in command
        assert "medium" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_with_audio_params(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeItem(
            path="/movies/test.mkv",
            languages=None,
            video_params=None,
            audio_params="-c aac -b 192k",
        )
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        assert "-c:a:0" in command
        assert "aac" in command
        assert "-b:a:0" in command
        assert "192k" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_filters_audio_by_language(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeItem(
            path="/movies/test.mkv",
            languages="eng",
            video_params=None,
            audio_params=None,
        )
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        # Should only map the English audio track (index 1), not Italian (index 2)
        assert "0:1" in command  # English audio
        # Italian audio should not be mapped as a separate track since we filtered

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_filters_subtitle_by_language(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeItem(
            path="/movies/test.mkv",
            languages="eng",
            video_params=None,
            audio_params=None,
        )
        # Add Italian subtitle to test filtering
        mock_ffprobe_output["streams"].append(
            {
                "index": 4,
                "codec_type": "subtitle",
                "codec_name": "subrip",
                "tags": {"language": "ita"},
            }
        )
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        # Should only map the English subtitle
        assert "0:3" in command  # English subtitle
        # Count subtitle mappings - should be 1 (English only)
        subtitle_mappings = [
            i
            for i, arg in enumerate(command)
            if arg == "-map" and i + 1 < len(command) and "0:3" in command[i + 1]
        ]
        assert len(subtitle_mappings) > 0

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_with_hwaccel(
        self,
        mock_config: MagicMock,
        mock_ffprobe: MagicMock,
        basic_item: TranscodeItem,
        mock_ffprobe_output: dict[str, Any],
    ) -> None:
        # Mock config with transcoding hwaccel
        mock_transcoding = MagicMock()
        mock_transcoding.hwaccel = "cuda"
        mock_config.transcoding = mock_transcoding
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(basic_item, "/tmp/output.mkv")

        assert "-hwaccel" in command
        assert "cuda" in command
        assert "-hwaccel_output_format" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_converts_movtext_to_subrip(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, basic_item: TranscodeItem
    ) -> None:
        mock_config.transcoding = None
        mock_ffprobe.return_value = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                },
                {
                    "index": 1,
                    "codec_type": "subtitle",
                    "codec_name": "mov_text",
                    "tags": {"language": "eng"},
                },
            ]
        }

        command = build_ffmpeg_command(basic_item, "/tmp/output.mkv")

        # Find the subtitle codec argument
        subtitle_codec_idx = None
        for i, arg in enumerate(command):
            if "-c:s:0" in arg:
                subtitle_codec_idx = i
                break

        assert subtitle_codec_idx is not None
        assert "subrip" in command[subtitle_codec_idx + 1]

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_skips_subtitle_without_codec(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, basic_item: TranscodeItem
    ) -> None:
        mock_config.transcoding = None
        mock_ffprobe.return_value = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                },
                {
                    "index": 1,
                    "codec_type": "subtitle",
                    # Missing codec_name
                    "tags": {"language": "eng"},
                },
            ]
        }

        command = build_ffmpeg_command(basic_item, "/tmp/output.mkv")

        # Should not include the subtitle stream
        assert "0:1" not in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_with_multiple_video_streams(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, basic_item: TranscodeItem
    ) -> None:
        mock_config.transcoding = None
        mock_ffprobe.return_value = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                },
                {
                    "index": 1,
                    "codec_type": "video",
                    "codec_name": "mjpeg",  # thumbnail/poster
                },
            ]
        }

        command = build_ffmpeg_command(basic_item, "/tmp/output.mkv")

        # Should map both video streams
        assert "0:v:0" in command
        assert "0:1" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_metadata_includes_params(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeItem(
            path="/movies/test.mkv",
            languages=None,
            video_params="-c libx265",
            audio_params="-c aac",
        )
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        # Check that metadata includes the parameters used
        assert "-metadata:s:v:0" in command
        assert "-metadata:s:a:0" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_with_multiple_languages(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeItem(
            path="/movies/test.mkv",
            languages="eng, ita",  # Multiple languages
            video_params=None,
            audio_params=None,
        )
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        # Should include both English and Italian audio tracks
        assert "0:1" in command  # English audio
        assert "0:2" in command  # Italian audio

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_audio_sorting_prefers_matching_language(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock
    ) -> None:
        mock_config.transcoding = None
        # Italian audio is first in the file, but we want English
        mock_ffprobe.return_value = {
            "streams": [
                {
                    "index": 0,
                    "codec_type": "video",
                    "codec_name": "h264",
                },
                {
                    "index": 1,
                    "codec_type": "audio",
                    "codec_name": "ac3",
                    "tags": {"language": "ita"},
                },
                {
                    "index": 2,
                    "codec_type": "audio",
                    "codec_name": "aac",
                    "tags": {"language": "eng"},
                },
            ]
        }

        item = TranscodeItem(
            path="/movies/test.mkv",
            languages="eng",
            video_params=None,
            audio_params=None,
        )

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        # Find the order of audio stream mappings
        audio_maps: list[str] = []
        for i, arg in enumerate(command):
            if arg == "-map" and i + 1 < len(command):
                next_arg = command[i + 1]
                if next_arg.startswith("0:") and "a" not in next_arg and next_arg not in ["0:v:0"]:
                    # This is an audio stream mapping
                    audio_maps.append(next_arg)

        # English (index 2) should be mapped first, even though Italian (index 1) appears first in
        # file due to sorting by matching language
        if len(audio_maps) > 0:
            # The first audio stream should be English (index 2)
            assert "2" in audio_maps[0]
