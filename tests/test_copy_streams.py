import pathlib
import shutil

import ffmpeg
import pytest

from wi1_bot.transcoder import Transcoder
from wi1_bot.transcoder.transcode_queue import TranscodeItem

FILES_PATH = pathlib.Path("./tests/files")


@pytest.fixture(autouse=True)
def setup_files():
    for file in FILES_PATH.glob("*.mkv"):
        shutil.copy(file, file.with_name(f"{file.name}.bak"))

    yield

    for file in FILES_PATH.glob("*-TRANSCODED.mkv"):
        file.unlink(missing_ok=True)

    for file in FILES_PATH.glob("*.bak"):
        file.rename(file.with_name(file.stem))


def test_copy_mjpeg():
    path = FILES_PATH / "h264_eac3_pgssub_mjpeg.mkv"

    item = TranscodeItem(
        path=str(path),
        copy_all_streams=True,
        video_codec="libx264",
        video_bitrate=2000000,
        audio_codec="aac",
        audio_channels=2,
        audio_bitrate="128k",
    )

    t = Transcoder()
    t._do_transcode(item)  # pyright: ignore[reportPrivateUsage]

    transcoded = path.with_name(f"{path.stem}-TRANSCODED.mkv")
    assert transcoded.exists()

    output = ffmpeg.probe(transcoded)
    streams = output["streams"]
    assert isinstance(streams, list)
    assert any(s["codec_type"] == "video" and s["codec_name"] == "mjpeg" for s in streams)
