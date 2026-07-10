import logging
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from time import sleep

from wi1_bot import __version__, push
from wi1_bot.arr import Radarr, Sonarr, replace_remote_paths
from wi1_bot.config import config
from wi1_bot.languages import keep_original_language

from .ffprobe import FfprobeException, Stream, ffprobe
from .transcode_queue import TranscodeItem, queue

# https://github.com/Radarr/Radarr/blob/e29be26fc9a5570bdf37a1b9504b3c0162be7715/src/NzbDrone.Core/Parser/Parser.cs#L134
CLEAN_RELEASE_GROUP_REGEX = re.compile(
    r"(-(RP|1|NZBGeek|Obfuscated|Obfuscation|Scrambled|sample|Pre|postbot|xpost|Rakuv[a-z0-9]*|WhiteRev|BUYMORE|AsRequested|AlternativeToRequested|GEROV|Z0iDS3N|Chamele0n|4P|4Planet|AlteZachen|RePACKPOST))+",
    re.IGNORECASE,
)
# https://github.com/Radarr/Radarr/blob/e29be26fc9a5570bdf37a1b9504b3c0162be7715/src/NzbDrone.Core/Parser/Parser.cs#L138
CLEAN_TORRENT_SUFFIX_REGEX = re.compile(r"\[(?:ettv|rartv|rarbg|cttv|publichd)\]", re.IGNORECASE)
# can't find where this is done in Radarr source
CLEAN_SITE_TAG_REGEX = re.compile(r"@(HDSpace)", re.IGNORECASE)


class SignalInterrupt(Exception):
    pass


class UnknownError(Exception):
    pass


class TranscodeResult(Enum):
    SUCCESS = auto()  # ffmpeg succeeded, move the transcoded file into place
    SKIP = auto()  # handled failure, drop the item from the queue
    RETRY = auto()  # handled failure, keep the item to try again later
    FAILED = auto()  # unhandled failure, eligible for a fallback attempt


@dataclass(frozen=True)
class TranscodeParams:
    """Concrete ffmpeg parameters for a single transcode attempt.

    Resolved from a quality profile (and the title's original language) at
    transcode time.
    """

    path: str
    languages: str | None = None
    video_params: str | None = None
    audio_params: str | None = None
    hwaccel: str | None = None


def sanitize_file_stem(stem: str) -> str:
    stem = stem.strip()
    stem = CLEAN_RELEASE_GROUP_REGEX.sub("", stem).strip()
    stem = CLEAN_TORRENT_SUFFIX_REGEX.sub("", stem).strip()
    stem = CLEAN_SITE_TAG_REGEX.sub("", stem).strip()
    return stem


def build_ffmpeg_command(params: TranscodeParams, transcode_to: Path | str) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-y",
    ]

    if params.hwaccel:
        command.extend(["-hwaccel", params.hwaccel])
        command.extend(["-hwaccel_output_format", params.hwaccel])

    command.extend(["-probesize", "100M"])
    command.extend(["-analyzeduration", "250M"])

    command.extend(["-i", params.path])

    command.extend(["-metadata", f"wi1_bot_version={__version__}"])

    langs: list[str] = []

    if params.languages:
        langs = [lang.strip() for lang in params.languages.split(",")]

    info = ffprobe(params.path)
    streams = info["streams"]

    command.extend(["-map", "0:v:0"])

    if params.video_params:
        parts = shlex.split(params.video_params)

        for param in parts:
            if param.startswith("-"):
                command.append(f"{param}:v:0")
            else:
                command.append(param)

        command.extend(["-metadata:s:v:0", f"params={params.video_params}"])
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
        key=lambda s: (
            0 if "tags" in s and "language" in s["tags"] and s["tags"]["language"] in langs else 1
        )
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

        if params.audio_params:
            parts = shlex.split(params.audio_params)

            for param in parts:
                if param.startswith("-"):
                    command.append(f"{param}:a:{aindex}")
                else:
                    command.append(param)

            command.extend([f"-metadata:s:a:{aindex}", f"params={params.audio_params}"])
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
        self.radarr = Radarr.from_config(config.radarr)
        self.sonarr = Sonarr.from_config(config.sonarr)

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

            self.logger.info(f"remaining queue size: {queue.size}")

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

        if config.transcoding is None or item.quality_profile not in config.transcoding.profiles:
            self.logger.warning(
                f"unknown quality profile '{item.quality_profile}' for {path.name},"
                " skipping transcoding"
            )
            return True

        profile = config.transcoding.profiles[item.quality_profile]

        languages = profile.languages
        if profile.keep_original_language:
            # don't strip a foreign-language title's original audio/subtitle tracks
            languages = keep_original_language(languages, item.original_language)

        # push.send(f"{basename}", title="starting transcode")

        # TODO: calculate compression amount
        # 1 - (video bitrate + audio bitrate) * duration / size
        # if compression amount > config value, transcode
        # else, don't transcode

        # duration = _get_duration(item.path)

        tmp_folder = Path(tempfile.gettempdir()) / "wi1-bot"
        tmp_folder.mkdir(exist_ok=True)

        stem = sanitize_file_stem(path.stem)
        transcode_to = tmp_folder / f"{stem}-TRANSCODED.mkv"

        tmp_log_path = tmp_folder / "wi1_bot.transcoder.log"

        # hwaccel is per-profile/per-fallback; omitting it means no hardware
        # acceleration, so the fallback can decode in software to recover from a
        # hardware-decoding failure
        params = TranscodeParams(
            path=item.path,
            languages=languages,
            video_params=profile.video_params,
            audio_params=profile.audio_params,
            hwaccel=profile.hwaccel,
        )

        result, status, last_output = self._run_ffmpeg(params, transcode_to, tmp_log_path)

        if result is TranscodeResult.FAILED and profile.fallback is not None:
            self.logger.warning(
                f"transcoding {path.name} failed, retrying with fallback parameters"
            )

            fallback = profile.fallback

            fallback_params = TranscodeParams(
                path=item.path,
                languages=languages,
                video_params=fallback.video_params,
                audio_params=fallback.audio_params,
                hwaccel=fallback.hwaccel,
            )

            result, status, last_output = self._run_ffmpeg(
                fallback_params, transcode_to, tmp_log_path
            )

        if result is TranscodeResult.SKIP:
            return True

        if result is TranscodeResult.RETRY:
            return False

        if result is TranscodeResult.FAILED:
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

    def _run_ffmpeg(
        self, params: TranscodeParams, transcode_to: Path, tmp_log_path: Path
    ) -> tuple[TranscodeResult, int, str]:
        """Run ffmpeg for a single attempt and classify the outcome.

        Writes the ffmpeg output to ``tmp_log_path`` (overwriting any previous
        attempt's log) and returns the outcome, exit status and last output line.
        """
        path = Path(params.path)

        command = build_ffmpeg_command(params, transcode_to)

        self.logger.debug(f"ffmpeg command: {shlex.join(command)}")

        with subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        ) as proc:
            last_output = ""

            with open(tmp_log_path, "w") as ffmpeg_log_file:
                ffmpeg_log_file.write(f"ffmpeg command: {shlex.join(command)}\n")
                assert proc.stdout is not None
                for line in proc.stdout:
                    ffmpeg_log_file.write(line)
                    last_output = line.strip()

            status = proc.wait()

        if status == 0:
            return TranscodeResult.SUCCESS, status, last_output

        try:
            transcode_to.unlink(missing_ok=True)
        except Exception:
            self.logger.debug(f"failed to delete transcoded file: {transcode_to}")

        if "Error opening input files" in last_output or "No such file or directory" in last_output:
            self.logger.info(f"file does not exist: {path}, skipping transcoding")
            return TranscodeResult.SKIP, status, last_output

        if "File name too long" in last_output:
            self.logger.info(f"file name is too long: {path}, skipping transcoding")
            return TranscodeResult.SKIP, status, last_output

        if "received signal 15" in last_output:
            self.logger.info(f"transcoding interrupted by signal: {path}, will retry")
            return TranscodeResult.RETRY, status, last_output

        if "cannot open shared object file" in last_output:
            self.logger.error("ffmpeg error: missing shared object file, will retry")
            push.send(f"ffmpeg error: {last_output}", title="ffmpeg error")
            return TranscodeResult.RETRY, status, last_output

        return TranscodeResult.FAILED, status, last_output

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
