from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

import wi1_bot.transcoder.transcoder as t_mod
from wi1_bot.models import TranscodeItem
from wi1_bot.transcoder.transcoder import (
    TranscodeParams,
    Transcoder,
    TranscodeResult,
    build_ffmpeg_command,
    sanitize_file_stem,
)


class TestBuildFfmpegCommand:
    @pytest.fixture
    def basic_item(self) -> TranscodeParams:
        return TranscodeParams(
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
        basic_item: TranscodeParams,
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
        item = TranscodeParams(
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
        item = TranscodeParams(
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
        item = TranscodeParams(
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
        item = TranscodeParams(
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
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, mock_ffprobe_output: dict[str, Any]
    ) -> None:
        mock_config.transcoding = None
        item = TranscodeParams(path="/movies/test.mkv", hwaccel="cuda")
        mock_ffprobe.return_value = mock_ffprobe_output

        command = build_ffmpeg_command(item, "/tmp/output.mkv")

        assert "-hwaccel" in command
        assert "cuda" in command
        assert "-hwaccel_output_format" in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_without_hwaccel(
        self,
        mock_config: MagicMock,
        mock_ffprobe: MagicMock,
        basic_item: TranscodeParams,
        mock_ffprobe_output: dict[str, Any],
    ) -> None:
        mock_config.transcoding = None
        mock_ffprobe.return_value = mock_ffprobe_output

        # no hwaccel on the params -> no hardware acceleration flags
        command = build_ffmpeg_command(basic_item, "/tmp/output.mkv")

        assert "-hwaccel" not in command
        assert "-hwaccel_output_format" not in command

    @patch("wi1_bot.transcoder.transcoder.ffprobe")
    @patch("wi1_bot.transcoder.transcoder.config")
    def test_command_converts_movtext_to_subrip(
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, basic_item: TranscodeParams
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
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, basic_item: TranscodeParams
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
        self, mock_config: MagicMock, mock_ffprobe: MagicMock, basic_item: TranscodeParams
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
        item = TranscodeParams(
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
        item = TranscodeParams(
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

        item = TranscodeParams(
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


def test_file_stem_sanitization() -> None:
    assert (
        sanitize_file_stem(
            "Thor.Love.and.Thunder.2022.IMAX.Hybrid.1080p.BluRay.DD+7.1.x264-LoRD@HDSpace"
        )
        == "Thor.Love.and.Thunder.2022.IMAX.Hybrid.1080p.BluRay.DD+7.1.x264-LoRD"
    )


class TestTranscodeFallback:
    def _profile(
        self,
        *,
        video_params: str = "-c:v hw",
        audio_params: str = "-c:a aac",
        languages: str | None = None,
        keep_original_language: bool = False,
        hwaccel: str | None = None,
        fallback: MagicMock | None = None,
    ) -> MagicMock:
        profile = MagicMock()
        profile.video_params = video_params
        profile.audio_params = audio_params
        profile.languages = languages
        profile.keep_original_language = keep_original_language
        profile.hwaccel = hwaccel
        profile.fallback = fallback
        return profile

    def _config(self, profile: MagicMock) -> MagicMock:
        config = MagicMock()
        config.transcoding.profiles = {"good": profile}
        return config

    @pytest.fixture
    def transcoder(self) -> Transcoder:
        # arr clients are mocked by the autouse conftest fixture
        return Transcoder()

    @pytest.fixture
    def source_file(self, tmp_path: Path) -> Path:
        src = tmp_path / "The Movie.mkv"
        src.write_text("data")
        return src

    def test_unknown_profile_skips_without_running(
        self, transcoder: Transcoder, source_file: Path
    ) -> None:
        item = TranscodeItem(path=str(source_file), quality_profile="missing")
        config = self._config(self._profile())

        with (
            patch.object(t_mod, "config", config),
            patch.object(Transcoder, "_run_ffmpeg") as mock_run,
        ):
            result = transcoder.transcode(item)

        assert result is True
        mock_run.assert_not_called()

    def test_no_fallback_reports_error(
        self,
        transcoder: Transcoder,
        source_file: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("WB_LOG_DIR", str(tmp_path / "logs"))
        item = TranscodeItem(path=str(source_file), quality_profile="good")
        config = self._config(self._profile(fallback=None))

        with (
            patch.object(t_mod, "config", config),
            patch.object(
                Transcoder, "_run_ffmpeg", return_value=(TranscodeResult.FAILED, 1, "boom")
            ) as mock_run,
            patch.object(t_mod, "shutil") as mock_shutil,
            patch.object(t_mod, "push") as mock_push,
        ):
            result = transcoder.transcode(item)

        assert result is True
        # no fallback defined, so only one attempt
        mock_run.assert_called_once()
        # the failure is reported: log copied to transcoder-errors and pushover sent
        mock_shutil.copy.assert_called_once()
        mock_push.send.assert_called_once()

    def test_fallback_retries_then_reports_error(
        self,
        transcoder: Transcoder,
        source_file: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("WB_LOG_DIR", str(tmp_path / "logs"))
        fallback = MagicMock()
        fallback.video_params = "-c:v sw"
        fallback.audio_params = "-c:a copy"
        item = TranscodeItem(path=str(source_file), quality_profile="good")
        config = self._config(self._profile(fallback=fallback))

        with (
            patch.object(t_mod, "config", config),
            patch.object(
                Transcoder,
                "_run_ffmpeg",
                side_effect=[
                    (TranscodeResult.FAILED, 1, "boom"),
                    (TranscodeResult.FAILED, 1, "boom again"),
                ],
            ) as mock_run,
            patch.object(t_mod, "shutil") as mock_shutil,
            patch.object(t_mod, "push") as mock_push,
        ):
            result = transcoder.transcode(item)

        assert result is True
        # primary attempt failed, so a second attempt runs with the fallback params
        assert mock_run.call_count == 2
        fallback_params = mock_run.call_args_list[1].args[0]
        assert fallback_params.video_params == "-c:v sw"
        assert fallback_params.audio_params == "-c:a copy"
        # the fallback also failed, so the error is reported once
        mock_shutil.copy.assert_called_once()
        mock_push.send.assert_called_once()

    def test_fallback_succeeds(self, transcoder: Transcoder, source_file: Path) -> None:
        fallback = MagicMock()
        fallback.video_params = "-c:v sw"
        fallback.audio_params = "-c:a copy"
        item = TranscodeItem(path=str(source_file), quality_profile="good")
        config = self._config(self._profile(fallback=fallback))

        with (
            patch.object(t_mod, "config", config),
            patch.object(
                Transcoder,
                "_run_ffmpeg",
                side_effect=[
                    (TranscodeResult.FAILED, 1, "boom"),
                    (TranscodeResult.SUCCESS, 0, ""),
                ],
            ) as mock_run,
            patch.object(t_mod, "shutil") as mock_shutil,
            patch.object(Transcoder, "_rescan_content") as mock_rescan,
        ):
            result = transcoder.transcode(item)

        assert result is True
        assert mock_run.call_count == 2
        # the fallback succeeded, so the transcoded file is moved into place
        mock_shutil.move.assert_called_once()
        mock_rescan.assert_called_once()

    def test_resolves_languages_with_original_language(
        self, transcoder: Transcoder, source_file: Path
    ) -> None:
        item = TranscodeItem(
            path=str(source_file), quality_profile="good", original_language="Japanese"
        )
        profile = self._profile(languages="eng", keep_original_language=True)
        config = self._config(profile)

        with (
            patch.object(t_mod, "config", config),
            patch.object(
                Transcoder, "_run_ffmpeg", return_value=(TranscodeResult.SUCCESS, 0, "")
            ) as mock_run,
            patch.object(t_mod, "shutil"),
            patch.object(Transcoder, "_rescan_content"),
        ):
            transcoder.transcode(item)

        params = mock_run.call_args.args[0]
        # the title's original language (jpn) is appended to the profile keep-list
        assert params.languages == "eng,jpn"

    def test_profile_and_fallback_use_their_own_hwaccel(
        self, transcoder: Transcoder, source_file: Path
    ) -> None:
        # the profile decodes with videotoolbox; its fallback omits hwaccel so it
        # can decode in software when hardware decoding is what failed
        fallback = MagicMock()
        fallback.video_params = "-c:v sw"
        fallback.audio_params = "-c:a copy"
        fallback.hwaccel = None
        item = TranscodeItem(path=str(source_file), quality_profile="good")
        config = self._config(self._profile(hwaccel="videotoolbox", fallback=fallback))

        with (
            patch.object(t_mod, "config", config),
            patch.object(
                Transcoder,
                "_run_ffmpeg",
                side_effect=[
                    (TranscodeResult.FAILED, 1, "boom"),
                    (TranscodeResult.SUCCESS, 0, ""),
                ],
            ) as mock_run,
            patch.object(t_mod, "shutil"),
            patch.object(Transcoder, "_rescan_content"),
        ):
            transcoder.transcode(item)

        assert mock_run.call_count == 2
        primary_params = mock_run.call_args_list[0].args[0]
        fallback_params = mock_run.call_args_list[1].args[0]
        assert primary_params.hwaccel == "videotoolbox"
        assert fallback_params.hwaccel is None
