import logging
import pathlib
import shlex
import shutil
import subprocess
import threading
from datetime import timedelta
from time import sleep
from typing import Any

from wi1_bot import push
from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config

from .transcode_queue import TranscodeItem, queue


class SignalInterrupt(Exception):
    pass


class UnknownError(Exception):
    pass


class Transcoder:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

        self.radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
        self.sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])

    def start(self) -> None:
        self.logger.info("starting transcoder")

        t = threading.Thread(target=self._worker)
        t.daemon = True
        t.start()

    def _worker(self) -> None:
        while True:
            item = queue.get_one()

            if item is None:
                sleep(3)
                continue

            try:
                remove = self._do_transcode(item)

                if remove:
                    queue.remove(item)
            except Exception:
                self.logger.warning(
                    "got exception when trying to transcode", exc_info=True
                )

            sleep(3)

    def _do_transcode(self, item: TranscodeItem) -> bool:
        path = pathlib.Path(item.path)

        self.logger.info(f"attempting to transcode {path.name}")

        if path.suffix == ".avi":
            self.logger.info(f"cannot transcode {path.name}: .avi not supported")
            return True

        # push.send(f"{basename}", title="starting transcode")

        # TODO: calculate compression amount
        # 1 - (video bitrate + audio bitrate) * duration / size
        # if compression amount > config value, transcode
        # else, don't transcode

        # duration = _get_duration(item.path)

        tmp_folder = pathlib.Path("/tmp/wi1-bot")
        tmp_folder.mkdir(exist_ok=True)

        transcode_to = tmp_folder / f"{path.stem}-TRANSCODED.mkv"

        command = self._build_ffmpeg_command(item, transcode_to)

        self.logger.debug(f"ffmpeg command: {shlex.join(command)}")

        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            last_output = ""

            tmp_log_path = tmp_folder / "wi1_bot.transcoder.log"

            with open(tmp_log_path, "w") as ffmpeg_log_file:
                assert proc.stdout is not None
                for line in proc.stdout:
                    ffmpeg_log_file.write(line)
                    last_output = line.strip()

            status = proc.wait()

            if status != 0:
                transcode_to.unlink(missing_ok=True)

                if "Error opening input files" in last_output:
                    self.logger.info(
                        f"file does not exist: {path}, skipping transcoding"
                    )
                    return True

                if "received signal 15" in last_output:
                    self.logger.info(
                        f"transcoding interrupted by signal: {path}, will retry"
                    )
                    return False

                if "cannot open shared object file" in last_output:
                    self.logger.error(
                        "ffmpeg error: missing shared object file, will retry"
                    )
                    push.send(f"ffmpeg error: {last_output}", title="ffmpeg error")
                    return False

                perm_log_path = tmp_folder / f"{path.stem}.log"

                if "general" in config and "log_dir" in config["general"]:
                    log_dir = pathlib.Path(config["general"]["log_dir"]).resolve()

                    perm_log_path = log_dir / "transcoder-errors" / f"{path.stem}.log"
                    perm_log_path.parent.mkdir(parents=True, exist_ok=True)

                shutil.copy(tmp_log_path, perm_log_path)

                self.logger.error(f"ffmpeg failed (status {status}): {last_output}")
                self.logger.error(f"log file: {perm_log_path}")

                push.send(
                    f"{path.name} has failed to transcode, log: {perm_log_path}",
                    title="transcoding error",
                )

                return True

        if not path.exists():
            self.logger.debug(
                f"file doesn't exist: {item.path}, deleting transcoded file"
            )

            transcode_to.unlink()
            return True

        new_path = path.parent / transcode_to.name
        shutil.move(transcode_to, new_path)
        path.unlink()

        self._rescan_content(item, str(new_path))

        self.logger.info(f"transcoded: {path.name} -> {new_path.name}")
        # push.send(f"{path.name} -> {new_path.name}", title="file transcoded")

        return True

    def _rescan_content(self, item: TranscodeItem, new_path: str) -> None:
        if item.content_id is not None:
            if new_path.startswith(config["radarr"]["root_folder"]):
                self.radarr.rescan_movie(item.content_id)
                # radarr bug that it doesn't see the deleted file and the new file
                # in one rescan?
                # have to sleep in between to ensure initial command finishes
                # or use pyarr.get_command() to see command status
                sleep(5)
                self.radarr.rescan_movie(item.content_id)
            elif new_path.startswith(config["sonarr"]["root_folder"]):
                self.sonarr.rescan_series(item.content_id)

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

    def _build_ffmpeg_command(
        self, item: TranscodeItem, transcode_to: pathlib.Path
    ) -> list[str]:
        command: list[Any] = [
            "ffmpeg",
            "-hide_banner",
            "-y",
        ]

        try:
            command.extend(["-hwaccel", config["transcoding"]["hwaccel"]])
            command.extend(["-hwaccel_output_format", config["transcoding"]["hwaccel"]])
        except KeyError:
            pass

        command.extend(["-probesize", "100M"])
        command.extend(["-analyzeduration", "250M"])

        command.extend(["-i", item.path])

        langs: list[str] = []

        if item.languages:
            langs = item.languages.split(",")

        # TODO: use ffprobe to figure out what streams we should copy
        # always copy first video stream
        # always copy first audio stream
        # always copy all subtitle streams
        # if languages is specified in the config:
        #     copy all audio streams in one of those languages
        # ffprobe -show_streams -print_format json {input_file} 2>/dev/null
        if item.copy_all_streams:
            command.extend(["-map", "0"])
        else:
            command.extend(["-map", "0:v:0"])

            command.extend(["-map", "0:a:0?"])

            if langs:
                command.extend([["-map", f"0:s:m:language:{lang}?"] for lang in langs])
            else:
                command.extend(["-map", "0:s?"])

        if item.video_codec:
            command.extend(["-vcodec", item.video_codec])
            command.extend(["-preset", "fast"])
            command.extend(["-profile:v", "main"])
        else:
            command.extend(["-vcodec", "copy"])

        if item.video_bitrate:
            command.extend(["-b:v", item.video_bitrate])
            command.extend(["-maxrate", item.video_bitrate * 2])
            command.extend(["-bufsize", item.video_bitrate * 2])

        if item.audio_codec:
            command.extend(["-acodec", item.audio_codec])
        else:
            command.extend(["-acodec", "copy"])

        if item.audio_channels:
            command.extend(["-ac", item.audio_channels])

        if item.audio_bitrate:
            command.extend(["-b:a", item.audio_bitrate])

        command.extend(["-scodec", "copy"])

        command.extend([transcode_to])

        return [str(arg) for arg in command]


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    t = Transcoder()
    t._worker()
