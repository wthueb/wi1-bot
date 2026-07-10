import pprint
import shutil
from pathlib import Path
from typing import Iterator
from unittest.mock import MagicMock, patch

import pytest

import wi1_bot.transcoder.transcoder as t_mod
from wi1_bot.models import TranscodeItem
from wi1_bot.transcoder import Transcoder, ffprobe

FILES_PATH = Path("./tests/files")


@pytest.fixture(autouse=True)
def setup_files() -> Iterator[None]:
    for file in FILES_PATH.iterdir():
        if file.is_file() and file.suffix in [".mkv", ".mp4"]:
            shutil.copy(file, file.with_name(f"{file.name}.bak"))

    yield

    for file in FILES_PATH.glob("*-TRANSCODED.mkv"):
        file.unlink(missing_ok=True)

    for file in FILES_PATH.glob("*.bak"):
        file.rename(file.with_name(file.stem))


def _profile(
    *,
    video_params: str | None = None,
    audio_params: str | None = None,
    languages: str | None = None,
) -> MagicMock:
    profile = MagicMock()
    profile.video_params = video_params
    profile.audio_params = audio_params
    profile.languages = languages
    profile.keep_original_language = False
    profile.hwaccel = None
    profile.fallback = None
    return profile


def _config(profile: MagicMock) -> MagicMock:
    config = MagicMock()
    config.transcoding.profiles = {"good": profile}
    return config


def test_copy_mjpeg() -> None:
    path = FILES_PATH / "h264_eac3_pgssub_mjpeg.mkv"

    item = TranscodeItem(path=str(path), quality_profile="good")
    profile = _profile(video_params="-c libx264 -b 2000k", audio_params="-c aac -b 128k -ac 2")

    t = Transcoder()
    with (
        patch.object(t_mod, "config", _config(profile)),
        patch.object(Transcoder, "_rescan_content"),
    ):
        t.transcode(item)

    transcoded = path.with_name(f"{path.stem}-TRANSCODED.mkv")
    assert transcoded.exists()

    output = ffprobe(transcoded)
    streams = output["streams"]
    assert isinstance(streams, list)
    pprint.pp(streams)

    assert any(
        s["codec_type"] == "video" and "codec_name" in s and s["codec_name"] == "mjpeg"
        for s in streams
    )


def test_convert_movtext() -> None:
    path = FILES_PATH / "h264_eac3_movtext.mp4"

    item = TranscodeItem(path=str(path), quality_profile="good")
    profile = _profile()

    t = Transcoder()
    with (
        patch.object(t_mod, "config", _config(profile)),
        patch.object(Transcoder, "_rescan_content"),
    ):
        t.transcode(item)

    transcoded = path.with_name(f"{path.stem}-TRANSCODED.mkv")
    assert transcoded.exists()

    output = ffprobe(transcoded)
    streams = output["streams"]
    assert isinstance(streams, list)
    pprint.pp(streams)

    assert any(
        s["codec_type"] == "subtitle" and "codec_name" in s and s["codec_name"] == "subrip"
        for s in streams
    )


def test_language_audio() -> None:
    path = FILES_PATH / "none_ita_eng_audio.mkv"

    item = TranscodeItem(path=str(path), quality_profile="good")
    profile = _profile(languages="eng")

    t = Transcoder()
    with (
        patch.object(t_mod, "config", _config(profile)),
        patch.object(Transcoder, "_rescan_content"),
    ):
        t.transcode(item)

    transcoded = path.with_name(f"{path.stem}-TRANSCODED.mkv")
    assert transcoded.exists()

    output = ffprobe(transcoded)
    streams = output["streams"]
    assert isinstance(streams, list)
    pprint.pp(streams)

    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    languages = [
        s["tags"]["language"] if "tags" in s and "language" in s["tags"] else None
        for s in audio_streams
    ]

    assert languages == ["eng", None]


def test_foreign_audio() -> None:
    path = FILES_PATH / "ita_audio.mkv"

    item = TranscodeItem(path=str(path), quality_profile="good")
    profile = _profile(languages="eng")

    t = Transcoder()
    with (
        patch.object(t_mod, "config", _config(profile)),
        patch.object(Transcoder, "_rescan_content"),
    ):
        t.transcode(item)

    transcoded = path.with_name(f"{path.stem}-TRANSCODED.mkv")
    assert transcoded.exists()

    output = ffprobe(transcoded)
    streams = output["streams"]
    assert isinstance(streams, list)
    pprint.pp(streams)

    audio_streams = [s for s in streams if s["codec_type"] == "audio"]
    languages = [
        s["tags"]["language"] if "tags" in s and "language" in s["tags"] else None
        for s in audio_streams
    ]

    assert languages == ["ita"]
