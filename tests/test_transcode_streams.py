import pprint
import shlex
import shutil
from pathlib import Path
from typing import Iterator

import pytest

from wi1_bot.models import TranscodeItem
from wi1_bot.transcoder import Transcoder, ffprobe
from wi1_bot.transcoder.transcoder import build_ffmpeg_command

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


def test_copy_mjpeg() -> None:
    path = FILES_PATH / "h264_eac3_pgssub_mjpeg.mkv"

    item = TranscodeItem(
        path=str(path),
        video_params="-c libx264 -b 2000k",
        audio_params="-c aac -b 128k -ac 2",
    )

    t = Transcoder()
    print(shlex.join(build_ffmpeg_command(item, "output.mkv")))
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

    item = TranscodeItem(path=str(path))

    t = Transcoder()
    print(shlex.join(build_ffmpeg_command(item, "output.mkv")))
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

    item = TranscodeItem(path=str(path), languages="eng")

    t = Transcoder()
    print(shlex.join(build_ffmpeg_command(item, "output.mkv")))
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

    item = TranscodeItem(path=str(path), languages="eng")

    t = Transcoder()
    print(shlex.join(build_ffmpeg_command(item, "output.mkv")))
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
