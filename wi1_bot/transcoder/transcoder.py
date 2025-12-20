import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from time import sleep

from wi1_bot import __version__, push
from wi1_bot.arr import Radarr, Sonarr, replace_remote_paths
from wi1_bot.config import config

from .ffprobe import FfprobeException, Stream, ffprobe
from .transcode_queue import TranscodeItem, queue

# https://github.com/Radarr/Radarr/blob/e29be26fc9a5570bdf37a1b9504b3c0162be7715/src/NzbDrone.Core/Parser/Parser.cs#L134
CLEAN_RELEASE_GROUP_REGEX = re.compile(
    r"(-(RP|1|NZBGeek|Obfuscated|Obfuscation|Scrambled|sample|Pre|postbot|xpost|Rakuv[a-z0-9]*|WhiteRev|BUYMORE|AsRequested|AlternativeToRequested|GEROV|Z0iDS3N|Chamele0n|4P|4Planet|AlteZachen|RePACKPOST))+",
    re.IGNORECASE,
)
# https://github.com/Radarr/Radarr/blob/e29be26fc9a5570bdf37a1b9504b3c0162be7715/src/NzbDrone.Core/Parser/Parser.cs#L138
CLEAN_TORRENT_SUFFIX_REGEX = re.compile(r"\[(?:ettv|rartv|rarbg|cttv|publichd)\]", re.IGNORECASE)


class SignalInterrupt(Exception):
    pass


class UnknownError(Exception):
    pass


def build_ffmpeg_command(item: TranscodeItem, transcode_to: Path | str) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
    ]

    if config.transcoding is not None and config.transcoding.hwaccel is not None:
        command.extend(["-hwaccel", config.transcoding.hwaccel])
        command.extend(["-hwaccel_output_format", config.transcoding.hwaccel])

    command.extend(["-probesize", "100M"])
    command.extend(["-analyzeduration", "250M"])

    command.extend(["-i", item.path])

    command.extend(["-metadata", f"wi1_bot_version={__version__}"])

    langs: list[str] = []

    if item.languages:
        langs = [lang.strip() for lang in item.languages.split(",")]

    info = ffprobe(item.path)
    streams = info["streams"]

    command.extend(["-map", "0:v:0"])

    if item.video_params:
        params = shlex.split(item.video_params)

        for param in params:
            if param.startswith("-"):
                command.append(f"{param}:v:0")
            else:
                command.append(param)

        command.extend(["-metadata:s:v:0", f"params={item.video_params}"])
    else:
        command.extend(["-c:v:0", "copy"])
        command.extend(["-metadata:s:v:0", "params=-c copy"])

    vindex = 0
    aindex = 0
    sindex = 0

    video_streams: list[Stream] = []
    audio_streams: list[Stream] = []
    subtitle_streams: list[Stream] = []

    for stream in streams:
        if stream["codec_type"] == "video":
            # already mapped main video stream above
            if vindex == 0:
                vindex += 1
                continue

            video_streams.append(stream)
        elif stream["codec_type"] == "audio":
            audio_streams.append(stream)
        elif stream["codec_type"] == "subtitle":
            # keep only streams that match specified languages
            if langs and (
                "tags" not in stream
                or "language" not in stream["tags"]
                or stream["tags"]["language"] not in langs
            ):
                continue

            # no codec specified, happens with some release groups
            if "codec_name" not in stream:
                continue

            subtitle_streams.append(stream)

    for stream in video_streams:
        command.extend(["-map", f"0:{stream['index']}"])
        command.extend([f"-c:v:{vindex}", "copy"])

        command.extend([f"-metadata:s:v:{vindex}", "params=-c copy"])
        vindex += 1

    audio_streams.sort(
        key=lambda s: 0
        if "tags" in s and "language" in s["tags"] and s["tags"]["language"] in langs
        else 1
    )

    audio_has_matching_lang = any(
        "tags" not in s or "language" not in s["tags"] or s["tags"]["language"] in langs
        for s in audio_streams
    )

    for stream in audio_streams:
        # keep matching languages and streams with no language specified
        if (
            audio_has_matching_lang
            and langs
            and "tags" in stream
            and "language" in stream["tags"]
            and stream["tags"]["language"] not in langs
        ):
            continue

        command.extend(["-map", f"0:{stream['index']}"])

        if item.audio_params:
            params = shlex.split(item.audio_params)

            for param in params:
                if param.startswith("-"):
                    command.append(f"{param}:a:{aindex}")
                else:
                    command.append(param)

            command.extend([f"-metadata:s:a:{aindex}", f"params={item.audio_params}"])
        else:
            command.extend([f"-c:a:{aindex}", "copy"])
            command.extend([f"-metadata:s:a:{aindex}", "params=-c copy"])

        aindex += 1

    for stream in subtitle_streams:
        command.extend(["-map", f"0:{stream['index']}"])

        codec = "copy"
        if "codec_name" in stream and stream["codec_name"] == "mov_text":
            codec = "subrip"
        command.extend([f"-c:s:{sindex}", codec])

        command.extend([f"-metadata:s:s:{sindex}", f"params=-c {codec}"])
        sindex += 1

    command.extend([str(transcode_to)])

    return command


class Transcoder:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

        self.radarr = Radarr(str(config.radarr.url), config.radarr.api_key)
        self.sonarr = Sonarr(str(config.sonarr.url), config.sonarr.api_key)

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

            remove = False

            try:
                remove = self.transcode(item)
            except FfprobeException:
                self.logger.warning("ffprobe failed, will not retry", exc_info=True)
                push.send(
                    f"{item.path} has failed to transcode due to ffprobe error",
                    title="transcoding error",
                )
                remove = True
            except Exception:
                self.logger.warning(
                    "got exception when trying to transcode, will retry", exc_info=True
                )

            if remove:
                queue.remove(item)

            sleep(3)

    def transcode(self, item: TranscodeItem) -> bool:
        path = Path(item.path)

        self.logger.info(f"attempting to transcode {path.name}")

        if path.suffix == ".avi":
            self.logger.info(f"cannot transcode {path.name}: .avi not supported")
            return True

        if not path.exists():
            self.logger.info(f"file does not exist: {item.path}, skipping transcoding")
            return True

        # push.send(f"{basename}", title="starting transcode")

        # TODO: calculate compression amount
        # 1 - (video bitrate + audio bitrate) * duration / size
        # if compression amount > config value, transcode
        # else, don't transcode

        # duration = _get_duration(item.path)

        tmp_folder = Path(tempfile.gettempdir()) / "wi1-bot"
        tmp_folder.mkdir(exist_ok=True)

        filename = path.stem
        filename = CLEAN_RELEASE_GROUP_REGEX.sub("", filename)
        filename = CLEAN_TORRENT_SUFFIX_REGEX.sub("", filename)
        transcode_to = tmp_folder / f"{filename}-TRANSCODED.mkv"

        command = build_ffmpeg_command(item, transcode_to)

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
                ffmpeg_log_file.write(f"ffmpeg command: {shlex.join(command)}\n")
                assert proc.stdout is not None
                for line in proc.stdout:
                    ffmpeg_log_file.write(line)
                    last_output = line.strip()

            status = proc.wait()

            if status != 0:
                try:
                    transcode_to.unlink(missing_ok=True)
                except Exception:
                    self.logger.debug(f"failed to delete transcoded file: {transcode_to}")

                if (
                    "Error opening input files" in last_output
                    or "No such file or directory" in last_output
                ):
                    self.logger.info(f"file does not exist: {path}, skipping transcoding")
                    return True

                if "File name too long" in last_output:
                    self.logger.info(f"file name is too long: {path}, skipping transcoding")
                    return True

                if "received signal 15" in last_output:
                    self.logger.info(f"transcoding interrupted by signal: {path}, will retry")
                    return False

                if "cannot open shared object file" in last_output:
                    self.logger.error("ffmpeg error: missing shared object file, will retry")
                    push.send(f"ffmpeg error: {last_output}", title="ffmpeg error")
                    return False

                perm_log_path = tmp_folder / f"{path.stem}.log"

                if log_dir_str := os.getenv("WB_LOG_DIR"):
                    log_dir = Path(log_dir_str).resolve()

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
            self.logger.debug(f"file doesn't exist: {item.path}, deleting transcoded file")

            transcode_to.unlink(missing_ok=True)
            return True

        new_path = path.parent / transcode_to.name
        shutil.move(transcode_to, new_path)
        path.unlink()

        self._rescan_content(new_path)

        self.logger.info(f"transcoded: {path.name} -> {new_path.name}")
        # push.send(f"{path.name} -> {new_path.name}", title="file transcoded")

        return True

    def _rescan_content(self, new_path: Path) -> None:
        radarr_root = replace_remote_paths(config.radarr.root_folder)
        sonarr_root = replace_remote_paths(config.sonarr.root_folder)

        if new_path.is_relative_to(radarr_root):
            for m in self.radarr.get_movies():
                movie_path = replace_remote_paths(Path(m["path"]))

                if new_path.is_relative_to(movie_path):
                    # have to rescan the movie twice: Radarr/Radarr#7668
                    # TODO: create function that waits for comand to finish
                    self.radarr.rescan_movie(m["id"])
                    sleep(5)
                    self.radarr.rescan_movie(m["id"])
                    break
        elif new_path.is_relative_to(sonarr_root):
            for s in self.sonarr.get_series():
                series_path = replace_remote_paths(Path(s["path"]))

                if new_path.is_relative_to(series_path):
                    self.sonarr.rescan_series(s["id"])
                    break


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)
    t = Transcoder()
    t._worker()  # pyright: ignore[reportPrivateUsage]
