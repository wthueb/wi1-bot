import json
import logging
import threading
from pathlib import Path
from typing import Any

from flask import Flask, request

from wi1_bot.arr import Radarr, Sonarr, replace_remote_paths
from wi1_bot.arr.common import ImportMode
from wi1_bot.config import config
from wi1_bot.transcoder.transcode_queue import queue

app = Flask(__name__)

logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger(__name__)

instances = [config.radarr, config.radarr4k, config.sonarr, config.sonarr4k]


def on_download(req: dict[str, Any]) -> None:
    matching_instances = [
        x for x in instances if x is not None and x.instance_name == req["instanceName"]
    ]

    if not matching_instances:
        raise Exception(f"got request for unknown instance {req['instanceName']}")

    if len(matching_instances) > 1:
        logger.warning("more than one instance name matches request, picking first one")

    instance = matching_instances[0]

    if "movie" in req:
        radarr = Radarr.from_config(instance)

        movie_json = radarr.get_movie_by_id(req["movie"]["id"])

        quality_profile = radarr.get_quality_profile_name(movie_json["qualityProfileId"])

        movie_folder = req["movie"]["folderPath"]
        relative_path = req["movieFile"]["relativePath"]

        path = Path(movie_folder) / relative_path

        if instance is config.radarr and config.radarr4k is not None:
            radarr4k = Radarr.from_config(config.radarr4k)

            if radarr4k.is_movie_monitored(movie_json["tmdbId"]):
                logger.info("pushing download to radarr4k")
                radarr4k.downloaded_movies_scan(path, import_mode=ImportMode.COPY)
            else:
                logger.debug("skipping 4k scan, movie not monitored in radarr4k")
    elif "series" in req:
        sonarr = Sonarr.from_config(instance)

        series_json = sonarr.get_series_by_id(req["series"]["id"])

        quality_profile = sonarr.get_quality_profile_name(series_json["qualityProfileId"])

        series_folder = req["series"]["path"]
        relative_path = req["episodeFile"]["relativePath"]

        path = Path(series_folder) / relative_path

        if instance is config.sonarr and config.sonarr4k is not None:
            sonarr4k = Sonarr.from_config(config.sonarr4k)

            tvdb_id = series_json["tvdbId"]

            monitored = any(
                sonarr4k.is_episode_monitored(
                    tvdb_id, episode["seasonNumber"], episode["episodeNumber"]
                )
                for episode in req.get("episodes", [])
            )

            if monitored:
                logger.info("pushing download to sonarr4k")
                sonarr4k.downloaded_episodes_scan(path, import_mode=ImportMode.COPY)
            else:
                logger.debug("skipping 4k scan, episode not monitored in sonarr4k")
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

        match request.json["eventType"]:
            case "Test":
                logger.info("got test event from arr")
            case "Download":
                on_download(request.json)
            case et:
                logger.warning(f"handler not setup for event type {et}")

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
