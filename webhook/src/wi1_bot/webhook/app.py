import json
import logging
from pathlib import Path
from time import perf_counter
from typing import Any

from flask import Flask, Response, g, request
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.arr.common import ImportMode
from wi1_bot.common import push
from wi1_bot.webhook.config import config
from wi1_bot.webhook.metrics import (
    CROSS_SCAN_OPERATIONS,
    EVENTS,
    HTTP_REQUEST_DURATION,
    HTTP_REQUESTS,
    HTTP_REQUESTS_IN_PROGRESS,
)
from wi1_bot.webhook.rescan import rescan_content
from wi1_bot.webhook.transcode_queue import queue

app = Flask(__name__)

logging.getLogger("werkzeug").disabled = True

logger = logging.getLogger(__name__)

instances = [config.radarr, config.radarr4k, config.sonarr, config.sonarr4k]

# clients used for the post-transcode rescan (Arr-native paths, no remote mapping)
radarr = Radarr.from_config(config.radarr)
sonarr = Sonarr.from_config(config.sonarr)

_KNOWN_HTTP_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT"})
_EVENT_TYPES = {
    "Test": "test",
    "Download": "download",
    "Grab": "grab",
    "EpisodeFileDelete": "episode_file_delete",
    "Health": "health",
    "HealthRestored": "health_restored",
}


def _http_method() -> str:
    return request.method if request.method in _KNOWN_HTTP_METHODS else "OTHER"


def _http_route() -> str:
    return request.url_rule.rule if request.url_rule is not None else "unmatched"


@app.before_request
def start_http_metrics() -> None:
    method = _http_method()
    route = _http_route()
    g.http_metrics = (method, route, perf_counter())
    HTTP_REQUESTS_IN_PROGRESS.labels(method=method, route=route).inc()


def _finish_http_metrics(status_code: int) -> None:
    request_metrics: tuple[str, str, float] | None = g.pop("http_metrics", None)
    if request_metrics is None:
        return

    method, route, started_at = request_metrics
    HTTP_REQUESTS.labels(method=method, route=route, status_code=str(status_code)).inc()
    HTTP_REQUEST_DURATION.labels(method=method, route=route).observe(perf_counter() - started_at)
    HTTP_REQUESTS_IN_PROGRESS.labels(method=method, route=route).dec()


@app.after_request
def finish_http_metrics(response: Response) -> Response:
    _finish_http_metrics(response.status_code)
    return response


@app.teardown_request
def finish_failed_http_metrics(_exception: BaseException | None) -> None:
    # Flask normally turns exceptions into a response and runs ``after_request``.
    # This covers exceptions propagated by testing or alternate server settings.
    _finish_http_metrics(500)


def _event_source(req: dict[str, Any]) -> str:
    instance_name = req.get("instanceName")
    configured_instances = (
        (config.radarr, "radarr"),
        (config.radarr4k, "radarr4k"),
        (config.sonarr, "sonarr"),
        (config.sonarr4k, "sonarr4k"),
    )
    for instance, source in configured_instances:
        if instance is not None and instance.instance_name == instance_name:
            return source

    if "movie" in req or "movieFiles" in req:
        return "radarr"
    if "series" in req or "episodes" in req or "episodeFiles" in req:
        return "sonarr"
    return "unknown"


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
        instance_radarr = Radarr.from_config(instance)

        movie_json = instance_radarr.get_movie_by_id(req["movie"]["id"])

        quality_profile = instance_radarr.get_quality_profile_name(movie_json["qualityProfileId"])

        movie_language = movie_json.get("originalLanguage")
        original_language = movie_language.get("name") if movie_language else None

        movie_folder = req["movie"]["folderPath"]
        relative_path = req["movieFile"]["relativePath"]

        path = Path(movie_folder) / relative_path

        if instance is config.radarr and config.radarr4k is not None:
            radarr4k = Radarr.from_config(config.radarr4k)
            try:
                if radarr4k.is_movie_monitored(movie_json["tmdbId"]):
                    logger.info("pushing download to radarr4k")
                    radarr4k.downloaded_movies_scan(path, import_mode=ImportMode.COPY)
                    cross_scan_outcome = "triggered"
                else:
                    logger.debug("skipping 4k scan, movie not monitored in radarr4k")
                    cross_scan_outcome = "not_monitored"
            except Exception:
                CROSS_SCAN_OPERATIONS.labels(target="radarr4k", outcome="error").inc()
                raise
            CROSS_SCAN_OPERATIONS.labels(target="radarr4k", outcome=cross_scan_outcome).inc()
    elif "series" in req:
        instance_sonarr = Sonarr.from_config(instance)

        series_json = instance_sonarr.get_series_by_id(req["series"]["id"])

        quality_profile = instance_sonarr.get_quality_profile_name(series_json["qualityProfileId"])

        series_language = series_json.get("originalLanguage")
        original_language = series_language.get("name") if series_language else None

        series_folder = req["series"]["path"]
        relative_path = req["episodeFile"]["relativePath"]

        path = Path(series_folder) / relative_path

        if instance is config.sonarr and config.sonarr4k is not None:
            sonarr4k = Sonarr.from_config(config.sonarr4k)

            tvdb_id = series_json["tvdbId"]
            try:
                monitored = any(
                    sonarr4k.is_episode_monitored(
                        tvdb_id, episode["seasonNumber"], episode["episodeNumber"]
                    )
                    for episode in req.get("episodes", [])
                )

                if monitored:
                    logger.info("pushing download to sonarr4k")
                    sonarr4k.downloaded_episodes_scan(path, import_mode=ImportMode.COPY)
                    cross_scan_outcome = "triggered"
                else:
                    logger.debug("skipping 4k scan, episode not monitored in sonarr4k")
                    cross_scan_outcome = "not_monitored"
            except Exception:
                CROSS_SCAN_OPERATIONS.labels(target="sonarr4k", outcome="error").inc()
                raise
            CROSS_SCAN_OPERATIONS.labels(target="sonarr4k", outcome=cross_scan_outcome).inc()
    else:
        raise ValueError("unknown download request")

    # enqueue every completed download as an Arr-native path; the worker maps it to
    # its own filesystem and resolves the quality profile (dropping ones it can't transcode)
    job_id = queue.add(
        path=str(path),
        quality_profile=quality_profile,
        original_language=original_language,
    )
    logger.info(
        f"enqueued transcode job {job_id} for {path} "
        f"(profile {quality_profile!r}, queue size {queue.size})",
        extra={"job_id": job_id},
    )


@app.route("/", methods=["POST"])
def index() -> Any:
    req = request.get_json(silent=True)
    if not isinstance(req, dict):
        EVENTS.labels(event_type="invalid", source="unknown", outcome="invalid").inc()
        return "", 400
    if not isinstance(req.get("eventType"), str):
        EVENTS.labels(event_type="invalid", source=_event_source(req), outcome="invalid").inc()
        return "", 400

    raw_event_type = req["eventType"]
    event_type = _EVENT_TYPES.get(raw_event_type, "unsupported")
    source = _event_source(req)

    try:
        logger.debug(f"got request: {json.dumps(req)}")

        match raw_event_type:
            case "Test":
                logger.info("got test event from arr")
                outcome = "ignored"
            case "Download":
                if "movieFiles" in req or "episodeFiles" in req:
                    logger.debug("ignoring On Import Complete event")
                    outcome = "ignored"
                else:
                    on_download(req)
                    outcome = "enqueued"
            case "Grab" | "EpisodeFileDelete" | "Health" | "HealthRestored" as et:
                logger.debug(f"ignoring {et} event")
                outcome = "ignored"
            case et:
                logger.warning(f"handler not setup for event type {et}")
                outcome = "unsupported"

    except Exception:
        EVENTS.labels(event_type=event_type, source=source, outcome="failed_internal").inc()
        logger.warning(f"error handling request: {request.data.decode()}", exc_info=True)
    else:
        EVENTS.labels(event_type=event_type, source=source, outcome=outcome).inc()

    return "", 200


@app.route("/health", methods=["GET"])
def health() -> Any:
    return "OK", 200


@app.route("/metrics", methods=["GET"])
def metrics() -> Response:
    return Response(generate_latest(), content_type=CONTENT_TYPE_LATEST)


@app.route("/jobs/claim", methods=["POST"])
def job_claim() -> Any:
    body: dict[str, Any] = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id") or "unknown"

    item = queue.claim(worker_id)

    if item is None:
        return "", 204

    logger.info(
        f"dispatched job {item.id} ({Path(item.path).name}) to worker {worker_id!r} "
        f"(attempt {item.attempts})",
        extra={"job_id": item.id, "worker_id": worker_id},
    )

    return {
        "id": item.id,
        "path": item.path,
        "quality_profile": item.quality_profile,
        "original_language": item.original_language,
        "heartbeat": config.webhook.heartbeat,
    }, 200


@app.route("/jobs/<int:item_id>/heartbeat", methods=["POST"])
def job_heartbeat(item_id: int) -> Any:
    body: dict[str, Any] = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id") or "unknown"

    log_extra = {"job_id": item_id, "worker_id": worker_id}

    logger.debug(f"got heartbeat for job {item_id} from worker {worker_id!r}", extra=log_extra)

    if queue.heartbeat(item_id, worker_id):
        return "", 200

    # the lease was lost (reclaimed/expired/finished) or belongs to another worker
    logger.warning(
        f"rejected heartbeat for job {item_id} from worker {worker_id!r} "
        "(lease expired, reclaimed, or held by another worker)",
        extra=log_extra,
    )
    return "", 409


@app.route("/jobs/<int:item_id>/complete", methods=["POST"])
def job_complete(item_id: int) -> Any:
    body: dict[str, Any] = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id") or "unknown"
    filename = body.get("filename")

    path = queue.complete(item_id, outcome="completed" if filename else "skipped")

    log_extra = {"job_id": item_id, "worker_id": worker_id}

    if path is None:
        logger.warning(
            f"got completion for unknown job {item_id} from worker {worker_id!r} "
            "(already completed or expired)",
            extra=log_extra,
        )
        return "", 404

    if filename:
        logger.info(f"job {item_id} completed by worker {worker_id!r}: {filename}", extra=log_extra)
        try:
            new_path = Path(path).parent / filename
            rescan_content(
                radarr,
                sonarr,
                config.radarr.root_folder,
                config.sonarr.root_folder,
                new_path,
            )
        except Exception:
            logger.warning(
                f"error rescanning after transcode of {filename}", exc_info=True, extra=log_extra
            )
    else:
        # no filename -> the worker skipped this job (e.g. unknown profile); just drop it
        logger.info(f"job {item_id} skipped by worker {worker_id!r}, dropped", extra=log_extra)

    return "", 200


@app.route("/jobs/<int:item_id>/fail", methods=["POST"])
def job_fail(item_id: int) -> Any:
    body: dict[str, Any] = request.get_json(silent=True) or {}
    worker_id = body.get("worker_id") or "unknown"
    reason = body.get("reason", "unknown error")
    retry = bool(body.get("retry", False))
    log_tail = body.get("log_tail")

    path = queue.fail(item_id, retry=retry)

    log_extra = {"job_id": item_id, "worker_id": worker_id}

    if path is not None:
        # terminal failure (not requeued) -> notify
        msg = f"{Path(path).name} failed to transcode: {reason}"
        if log_tail:
            msg = f"{msg}\n{log_tail}"
        logger.error(msg, extra=log_extra)
        push.send(config.pushover, msg, title="transcoding error")
    else:
        logger.warning(
            f"job {item_id} from worker {worker_id!r} failed, requeued: {reason}", extra=log_extra
        )

    return "", 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.webhook.port)
