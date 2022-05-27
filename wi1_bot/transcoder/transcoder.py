import logging
import os
import shutil
import subprocess
import threading
from datetime import timedelta
from multiprocessing.connection import Connection
from time import sleep

from wi1_bot import push
from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config

from .transcode_queue import TranscodeItem, queue


class Transcoder:
    def __init__(self, ffmpeg_output: Connection | None = None) -> None:
        self.logger = logging.getLogger(__name__)
        self.ffmpeg_output = ffmpeg_output

        self.radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
        self.sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])

    def start(self) -> None:
        self.logger.debug("starting transcoder")

        t = threading.Thread(target=self._worker)
        t.daemon = True
        t.start()

    def do_transcode(self, item: TranscodeItem) -> bool:
        basename = item.path.split("/")[-1]

        self.logger.debug(f"attempting to transcode {basename}")

        if basename.endswith(".avi"):
            self.logger.debug(f"cannot transcode {basename}: .avi not supported")
            return True

        # push.send(f"{basename}", title="starting transcode")

        # TODO: calculate compression amount
        # 1 - (video bitrate + audio bitrate) * duration / size
        # if compression amount > config value, transcode
        # else, don't transcode

        # duration = _get_duration(item.path)

        tmp_path = os.path.join("/tmp/", basename)

        command = self._build_ffmpeg_command(item, tmp_path)

        self.logger.debug(f"ffmpeg command: {' '.join(command)}")

        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            last_output = "???"

            # pattern = re.compile(
            #     r".*time=(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+\.?\d+).*speed=(?P<speed>.*?)x"  # noqa: E501
            # )

            for line in proc.stdout:  # type: ignore
                if self.ffmpeg_output is not None:
                    self.ffmpeg_output.send(line)

                last_output = line.strip()

            status = proc.wait()

            if status != 0:
                self.logger.error(f"ffmpeg failed (status {status}): {last_output}")

                if "received signal 15" in last_output:
                    return False

                return True

        folder = item.path[: item.path.rfind("/")]

        filename, extension = basename[: basename.rfind(".")], basename.split(".")[-1]

        new_basename = f"{filename}-TRANSCODED.{extension}"

        new_path = os.path.join(folder, new_basename)

        if not os.path.exists(item.path):
            self.logger.debug(
                f"file doesn't exist: {item.path}, deleting transcoded file"
            )

            os.remove(tmp_path)

            return True

        shutil.move(tmp_path, new_path)
        os.remove(item.path)

        # FIXME: don't hardcode library paths (config)
        if item.content_id is not None:
            if new_path.startswith("/media/plex/movies/"):
                self.radarr.rescan_movie(item.content_id)
            elif new_path.startswith("/media/plex/shows/"):
                self.sonarr.rescan_series(item.content_id)

        self.logger.info(f"transcoded: {basename} -> {new_basename}")
        push.send(f"{basename} -> {new_basename}", title="file transcoded")

        return True

    def _worker(self) -> None:
        while True:
            item = queue.get_one()

            if item is None:
                sleep(3)
                continue

            try:
                if self.do_transcode(item):
                    queue.remove(item)
            except FileNotFoundError:
                self.logger.debug(
                    f"file does not exist: {item.path}, skipping transcoding"
                )
            except Exception:
                self.logger.warning(
                    "got exception when trying to transcode", exc_info=True
                )

            sleep(3)

    def _get_duration(self, path: str) -> timedelta:
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

    def _build_ffmpeg_command(self, item: TranscodeItem, tmp_path: str) -> list[str]:
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    t = Transcoder()
    t.start()
