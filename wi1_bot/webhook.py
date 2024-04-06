import json
import logging
import pathlib
import threading
from typing import Any

from flask import Flask, request

from wi1_bot import push, transcoder
from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import RemotePathMapping, config

app = Flask(__name__)

logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger(__name__)

radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])


def on_grab(req: dict[str, Any]) -> None:
    push.send(
        req["release"]["releaseTitle"], title=f"file grabbed ({req['downloadClient']})"
    )


def replace_remote_paths(path: pathlib.Path) -> pathlib.Path:
    if "general" not in config or "remote_path_mappings" not in config["general"]:
        return path

    mappings = config["general"]["remote_path_mappings"]

    most_specific: RemotePathMapping | None = None

    for mapping in mappings:
        if path.is_relative_to(mapping["remote"]):
            mapping_len = len(pathlib.Path(mapping["remote"]).parts)
            most_specific_len = (
                len(pathlib.Path(most_specific["remote"]).parts)
                if most_specific is not None
                else 0
            )

            if mapping_len > most_specific_len:
                most_specific = mapping

    if most_specific is not None:
        remote_path = path
        path = pathlib.Path(most_specific["local"]) / path.relative_to(
            most_specific["remote"]
        )

        logger.debug(f"replaced remote path mapping: {remote_path} -> {path}")

    return path


def on_download(req: dict[str, Any]) -> None:
    path: pathlib.Path
    content_id: int

    if "movie" in req:
        content_id = req["movie"]["id"]
        movie_json = radarr._radarr.get_movie(content_id)
        assert isinstance(movie_json, dict)

        quality_profile = radarr.get_quality_profile_name(
            movie_json["qualityProfileId"]
        )

        movie_folder = req["movie"]["folderPath"]
        relative_path = req["movieFile"]["relativePath"]

        path = pathlib.Path(movie_folder) / relative_path

        if not req["isUpgrade"]:
            push.send(path.name, title="new movie downloaded")
    elif "series" in req:
        content_id = req["series"]["id"]
        series_json = sonarr._sonarr.get_series(content_id)
        assert isinstance(series_json, dict)

        quality_profile = sonarr.get_quality_profile_name(
            series_json["qualityProfileId"]
        )

        series_folder = req["series"]["path"]
        relative_path = req["episodeFile"]["relativePath"]

        path = pathlib.Path(series_folder) / relative_path

        if not req["isUpgrade"]:
            push.send(path.name, title="new episode downloaded")
    else:
        raise ValueError("unknown download request")

    path = replace_remote_paths(path)

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
    languages = get_key(quality_options, "languages")
    video_codec = get_key(quality_options, "video_codec")
    video_bitrate = get_key(quality_options, "video_bitrate")
    audio_codec = get_key(quality_options, "audio_codec")
    audio_channels = get_key(quality_options, "audio_channels")
    audio_bitrate = get_key(quality_options, "audio_bitrate")

    transcoder.queue.add(
        path=str(path),
        content_id=content_id,
        copy_all_streams=copy_all_streams,
        languages=languages,
        video_codec=video_codec,
        video_bitrate=video_bitrate,
        audio_codec=audio_codec,
        audio_channels=audio_channels,
        audio_bitrate=audio_bitrate,
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
        logger.warning(
            f"error handling request: {request.data.decode()}", exc_info=True
        )

    return "", 200


def start() -> None:
    logger.info("starting webhook listener")

    t = threading.Thread(target=app.run, kwargs={"host": "0.0.0.0", "port": 9000})
    t.daemon = True
    t.start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
