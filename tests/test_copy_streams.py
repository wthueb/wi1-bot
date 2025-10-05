import pathlib
import shlex
import shutil

import pytest

from wi1_bot.transcoder import Transcoder, ffprobe
from wi1_bot.transcoder.transcode_queue import TranscodeItem
from wi1_bot.transcoder.transcoder import build_ffmpeg_command

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
    assert any(s["codec_type"] == "video" and s["codec_name"] == "mjpeg" for s in streams)
