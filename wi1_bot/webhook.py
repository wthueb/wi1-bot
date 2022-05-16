import logging
import os.path
import threading

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
        movie_json = radarr._radarr.get_movie_by_movie_id(req["movie"]["id"])

        quality_profile = radarr.get_quality_profile_name(
            movie_json["qualityProfileId"]
        )

        movie_folder = req["movie"]["folderPath"]
        basename = req["movieFile"]["relativePath"]

        push.send(basename, title="movie downloaded")

        path = os.path.join(movie_folder, basename)

        content_id = movie_json["id"]
    elif "series" in req:
        series_json = sonarr._sonarr.get_series(req["series"]["id"])
        quality_profile = sonarr.get_quality_profile_name(
            series_json["qualityProfileId"]
        )

        series_folder = req["series"]["path"]
        basename = req["episodeFile"]["relativePath"].split("/")[-1]

        push.send(basename, title="episode downloaded")

        path = os.path.join(series_folder, req["episodeFile"]["relativePath"])

        content_id = series_json["id"]
    else:
        raise ValueError("unknown download request")

    try:
        quality_options = config["transcoding"]["profiles"][quality_profile]
    except KeyError:
        return

    def get_key(d, k):
        try:
            return d[k]
        except KeyError:
            return None

    video_codec = get_key(quality_options, "video_codec")
    video_bitrate = get_key(quality_options, "video_bitrate")
    audio_codec = get_key(quality_options, "audio_codec")
    audio_channels = get_key(quality_options, "audio_channels")
    audio_bitrate = get_key(quality_options, "audio_bitrate")

    transcoder.queue.add(
        path=path,
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

        logger.debug(f"got request: {request.data}")

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
