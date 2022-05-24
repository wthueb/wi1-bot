import logging
import os
import shutil
import subprocess
import threading
from datetime import timedelta
from time import sleep

from wi1_bot import push
from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config

from .transcode_queue import TranscodeItem, queue

logger = logging.getLogger(__name__)

radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])


def _get_duration(path: str) -> timedelta:
    probe_command = [
        "ffprobe",
        "-hide_banner",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        path,
    ]

    probe_result = subprocess.run(probe_command, capture_output=True, text=True)

    try:
        duration = timedelta(seconds=float(probe_result.stdout.strip()))
    except ValueError:
        raise FileNotFoundError

    return duration


def _build_ffmpeg_command(item: TranscodeItem, tmp_path: str) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
    ]

    try:
        command.extend(["-hwaccel", config["transcoding"]["hwaccel"]])
    except KeyError:
        pass

    command.extend(["-i", item.path])

    if item.video_codec:
        command.extend(
            ["-c:v", item.video_codec, "-preset", "fast", "-profile:v", "main"]
        )
    else:
        command.extend(["-c:v", "copy"])

    if item.video_bitrate:
        command.extend(
            [
                "-b:v",
                str(item.video_bitrate),
                "-maxrate",
                str(item.video_bitrate * 2),
                "-bufsize",
                str(item.video_bitrate * 2),
            ]
        )

    if item.audio_codec:
        command.extend(["-c:a", item.audio_codec])
    else:
        command.extend(["-c:a", "copy"])

    if item.audio_channels:
        command.extend(["-ac", str(item.audio_channels)])

    if item.audio_bitrate:
        command.extend(["-b:a", str(item.audio_bitrate)])

    command.extend(["-c:s", "copy", tmp_path])

    return command


def do_transcode(item: TranscodeItem):
    basename = item.path.split("/")[-1]

    logger.debug(f"attempting to transcode {basename}")

    if basename.endswith(".avi"):
        logger.debug(f"cannot transcode {basename}: .avi not supported")
        return

    # push.send(f"{basename}", title="starting transcode")

    # TODO: calculate compression amount
    # (video bitrate + audio bitrate) * duration / current size
    # if compression amount not > config value, don't transcode
    # if compression amount > 1, don't transcode

    # duration = _get_duration(item.path)

    tmp_path = os.path.join("/tmp/", basename)

    command = _build_ffmpeg_command(item, tmp_path)

    logger.debug(f"ffmpeg command: {' '.join(command)}")

    with subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    ) as proc:
        output: list[str] = []

        # pattern = re.compile(
        #     r".*time=(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+\.?\d+).*speed=(?P<speed>.*?)x"  # noqa: E501
        # )

        for line in proc.stdout:  # type: ignore
            output.append(line)

            # TODO

            # match = pattern.search(line)

            # if not match:
            #     continue

            # curtime = timedelta(
            #     hours=int(match.group("hours")),
            #     minutes=int(match.group("minutes")),
            #     seconds=float(match.group("seconds")),
            # )

            # percent_done = curtime / duration

            # speed = float(match.group("speed"))

            # # careful of zero division
            # time_remaining = (duration - curtime) / speed

        status = proc.wait()

        if status != 0:
            logger.error(f"ffmpeg failed: {output[-1].strip()}")
            return

    folder = item.path[: item.path.rfind("/")]

    filename, extension = basename[: basename.rfind(".")], basename.split(".")[-1]

    new_basename = f"{filename}-TRANSCODED.{extension}"

    new_path = os.path.join(folder, new_basename)

    if not os.path.exists(item.path):
        logger.debug(f"file doesn't exist: {item.path}, deleting transcoded file")

        os.remove(tmp_path)

        return

    shutil.move(tmp_path, new_path)
    os.remove(item.path)

    if item.content_id is not None:
        if new_path.startswith("/media/plex/movies/"):
            radarr.refresh_movie(item.content_id)
        elif new_path.startswith("/media/plex/shows/"):
            sonarr.refresh_series(item.content_id)

    logger.info(f"transcoded: {basename} -> {new_basename}")
    push.send(f"{basename} -> {new_basename}", title="file transcoded")


def worker() -> None:
    while True:
        item = queue.get_one()

        if item is None:
            sleep(3)
            continue

        try:
            do_transcode(item)
        except FileNotFoundError:
            logger.debug(f"file does not exist: {item.path}, skipping transcoding")
        except Exception:
            logger.warning("got exception when trying to transcode", exc_info=True)

        queue.remove(item)

        sleep(3)


def start() -> None:
    logger.debug("starting transcoder")

    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    worker()
