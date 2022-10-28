import logging
import os.path
import threading
from typing import Any

from flask import Flask, request

from wi1_bot import push, transcoder
from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config

app = Flask(__name__)

logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger(__name__)

radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])


def on_grab(req: dict) -> None:
    push.send(
        req["release"]["releaseTitle"], title=f"file grabbed ({req['downloadClient']})"
    )


def on_download(req: dict) -> None:
    if "movie" in req:
        content_id = req["movie"]["id"]

        quality_profile = radarr.get_quality_profile_name(
            radarr._radarr.get_movie_by_movie_id(content_id)["qualityProfileId"]
        )

        movie_folder = req["movie"]["folderPath"]
        basename = req["movieFile"]["relativePath"]

        push.send(basename, title="movie downloaded")

        path = os.path.join(movie_folder, basename)
    elif "series" in req:
        content_id = req["series"]["id"]

        quality_profile = sonarr.get_quality_profile_name(
            sonarr._sonarr.get_series(content_id)["qualityProfileId"]
        )

        series_folder = req["series"]["path"]
        relative_path = req["episodeFile"]["relativePath"]

        push.send(relative_path.split("/")[-1], title="episode downloaded")

        path = os.path.join(series_folder, relative_path)
    else:
        raise ValueError("unknown download request")

    try:
        quality_options = config["transcoding"]["profiles"][quality_profile]
    except KeyError:
        return

    # python 3.11: TranscodingProfile and typing.LiteralString
    def get_key(d: Any, k: str) -> Any:
        try:
            return d[k]
        except KeyError:
            return None

    copy_all_streams = get_key(quality_options, "copy_all_streams")

    video_codec = get_key(quality_options, "video_codec")
    video_bitrate = get_key(quality_options, "video_bitrate")
    audio_codec = get_key(quality_options, "audio_codec")
    audio_channels = get_key(quality_options, "audio_channels")
    audio_bitrate = get_key(quality_options, "audio_bitrate")

    transcoder.queue.add(
        path=path,
        copy_all_streams=copy_all_streams,
        video_codec=video_codec,
        video_bitrate=video_bitrate,
        audio_codec=audio_codec,
        audio_channels=audio_channels,
        audio_bitrate=audio_bitrate,
        content_id=content_id,
    )


@app.route("/", methods=["POST"])
def index():
    try:
        if request.json is None or "eventType" not in request.json:
            return "", 400

        logger.debug(f"got request: {request.json}")

        if request.json["eventType"] == "Grab":
            on_grab(request.json)
        elif request.json["eventType"] == "Download":
            on_download(request.json)
    except Exception:
        logger.warning(f"error handling request: {request.data}", exc_info=True)

    return "", 200


def start() -> None:
    logger.debug("starting webhook listener")

    t = threading.Thread(target=app.run, kwargs={"host": "localhost", "port": 9000})
    t.daemon = True
    t.start()


if __name__ == "__main__":
    app.run(host="localhost", port=9000)
