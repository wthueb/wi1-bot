import json
import logging
import threading
from pathlib import Path
from typing import Any

from flask import Flask, request

from wi1_bot import push
from wi1_bot.arr import Radarr, Sonarr, replace_remote_paths
from wi1_bot.config import config
from wi1_bot.transcoder.transcode_queue import queue

app = Flask(__name__)

logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger(__name__)

radarr = Radarr(str(config.radarr.url), config.radarr.api_key)
sonarr = Sonarr(str(config.sonarr.url), config.sonarr.api_key)


def on_grab(req: dict[str, Any]) -> None:
    push.send(req["release"]["releaseTitle"], title=f"file grabbed ({req['downloadClient']})")


def on_download(req: dict[str, Any]) -> None:
    path: Path

    if "movie" in req:
        movie_json = radarr._radarr.get_movie(req["movie"]["id"])  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportPrivateUsage]
        assert isinstance(movie_json, dict)

        quality_profile = radarr.get_quality_profile_name(movie_json["qualityProfileId"])  # pyright: ignore[reportUnknownArgumentType]

        movie_folder = req["movie"]["folderPath"]
        relative_path = req["movieFile"]["relativePath"]

        path = Path(movie_folder) / relative_path

        if not req["isUpgrade"]:
            push.send(path.name, title="new movie downloaded")
    elif "series" in req:
        series_json = sonarr._sonarr.get_series(req["series"]["id"])  # pyright: ignore[reportPrivateUsage]
        assert isinstance(series_json, dict)

        quality_profile = sonarr.get_quality_profile_name(series_json["qualityProfileId"])  # pyright: ignore[reportUnknownArgumentType]

        series_folder = req["series"]["path"]
        relative_path = req["episodeFile"]["relativePath"]

        path = Path(series_folder) / relative_path

        if not req["isUpgrade"]:
            push.send(path.name, title="new episode downloaded")
    else:
        raise ValueError("unknown download request")

    if config.transcoding is None:
        return

    if quality_profile not in config.transcoding.profiles:
        logger.info(f"skipping transcoding for unknown quality profile '{quality_profile}'")
        return

    path = replace_remote_paths(path)

    quality_options = config.transcoding.profiles[quality_profile]
    languages = quality_options.languages
    video_params = quality_options.video_params
    audio_params = quality_options.audio_params

    queue.add(
        path=str(path),
        languages=languages,
        video_params=video_params,
        audio_params=audio_params,
    )


@app.route("/", methods=["POST"])
def index() -> Any:
    try:
        if request.json is None or "eventType" not in request.json:
            return "", 400

        logger.debug(f"got request: {json.dumps(request.json)}")

        if request.json["eventType"] == "Download":
            on_download(request.json)
    except Exception:
        logger.warning(f"error handling request: {request.data.decode()}", exc_info=True)

    return "", 200


@app.route("/health", methods=["GET"])
def health() -> Any:
    return "OK", 200


def start() -> None:
    logger.info("starting webhook listener")

    t = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 9000})
    t.daemon = True
    t.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
