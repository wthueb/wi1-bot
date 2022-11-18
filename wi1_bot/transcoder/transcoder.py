import logging
import pathlib
import shutil
import subprocess
import threading
from datetime import timedelta
from time import sleep

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
        self.logger.debug("starting transcoder")

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
                self._do_transcode(item)
                queue.remove(item)
            except SignalInterrupt:
                self.logger.debug(
                    f"transcoding interrupted by signal: {item.path}, will retry"
                )
            except FileNotFoundError:
                self.logger.debug(
                    f"file does not exist: {item.path}, skipping transcoding"
                )
                queue.remove(item)
            except UnknownError:
                queue.remove(item)
            except Exception:
                self.logger.warning(
                    "got exception when trying to transcode", exc_info=True
                )

            sleep(3)

    def _do_transcode(self, item: TranscodeItem) -> None:
        path = pathlib.Path(item.path)

        self.logger.debug(f"attempting to transcode {path.name}")

        if path.suffix == ".avi":
            self.logger.debug(f"cannot transcode {path.name}: .avi not supported")
            return

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

        self.logger.debug(f"ffmpeg command: {' '.join(command)}")

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
                for line in proc.stdout:  # type: ignore
                    ffmpeg_log_file.write(line)
                    last_output = line.strip()

            status = proc.wait()

            if status != 0:
                self.logger.error(f"ffmpeg failed (status {status}): {last_output}")

                if "No such file or directory" in last_output:
                    raise FileNotFoundError

                if "received signal 15" in last_output:
                    raise SignalInterrupt

                perm_log_path = tmp_folder / f"{path.stem}.log"
                shutil.copy(tmp_log_path, perm_log_path)
                self.logger.error(f"log file: {perm_log_path}")

                raise UnknownError

        new_path = path.parent / transcode_to.name

        if not path.exists():
            self.logger.debug(
                f"file doesn't exist: {item.path}, deleting transcoded file"
            )

            transcode_to.unlink()
            return

        shutil.move(transcode_to, new_path)
        path.unlink()

        self._rescan_content(item, str(new_path))

        self.logger.info(f"transcoded: {path.name} -> {new_path.name}")
        push.send(f"{path.name} -> {new_path.name}", title="file transcoded")

    def _rescan_content(self, item: TranscodeItem, new_path: str) -> None:
        # FIXME: don't hardcode library paths (config)
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
        command = [
            "ffmpeg",
            "-hide_banner",
            "-y",
        ]

        try:
            command.extend(["-hwaccel", config["transcoding"]["hwaccel"]])
            command.extend(["-hwaccel_output_format", config["transcoding"]["hwaccel"]])
        except KeyError:
            pass

        command.extend(["-i", item.path])

        if item.copy_all_streams:
            command.extend(["-map", "0"])

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

        command.extend(["-c:s", "copy", str(transcode_to)])

        return command


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    t = Transcoder()
    t._worker()
