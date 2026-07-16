import logging
import threading
import time
from typing import Any

import requests

from wi1_bot.transcoder.config import config
from wi1_bot.transcoder.transcoder import JobResult, Transcoder

logger = logging.getLogger(__name__)


class _Heartbeat:
    """Periodically extends a claimed job's lease while it is being transcoded.

    A transcode can outlive the webhook's lease; heartbeats keep the lease alive so
    the job isn't re-dispatched to another worker mid-transcode. If this worker
    crashes, heartbeats stop and the lease expires, letting the webhook reclaim it.
    """

    def __init__(self, base_url: str, job_id: int, worker_name: str, interval: float) -> None:
        self._url = f"{base_url}/jobs/{job_id}/heartbeat"
        self._job_id = job_id
        self._payload = {"worker_id": worker_name}
        self._log_extra = {"job_id": job_id, "worker_id": worker_name}
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            logger.debug(f"sending heartbeat for job {self._job_id}", extra=self._log_extra)

            try:
                resp = requests.post(self._url, json=self._payload, timeout=30)
            except requests.RequestException:
                logger.warning(
                    f"heartbeat for job {self._job_id} failed to send",
                    exc_info=True,
                    extra=self._log_extra,
                )
                continue

            if resp.status_code == 409:
                # the webhook no longer thinks we hold the lease; the job may have been
                # reclaimed and re-dispatched to another worker while we keep transcoding
                logger.warning(
                    f"heartbeat for job {self._job_id} rejected (409): lease lost, "
                    "job may have been reclaimed by another worker",
                    extra=self._log_extra,
                )
            elif not resp.ok:
                logger.error(
                    f"heartbeat for job {self._job_id} got unexpected {resp.status_code}",
                    extra=self._log_extra,
                )
            else:
                logger.debug(f"heartbeat for job {self._job_id} ok", extra=self._log_extra)

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()


def _post(url: str, payload: dict[str, Any], log_extra: dict[str, Any]) -> None:
    try:
        resp = requests.post(url, json=payload, timeout=30)
    except requests.RequestException:
        # if the report doesn't land, the lease will expire and the job is re-dispatched
        logger.warning(
            f"failed to report job outcome to {url}, lease will expire",
            exc_info=True,
            extra=log_extra,
        )
        return

    if not resp.ok:
        logger.warning(
            f"webhook returned {resp.status_code} for {url}: {resp.text!r}", extra=log_extra
        )
    else:
        logger.debug(f"reported to {url} -> {resp.status_code}", extra=log_extra)


def _claim(base_url: str, worker_name: str) -> dict[str, Any] | None:
    """Ask the webhook for a job.

    Returns the job dict, or ``None`` if the queue is empty or the webhook returned an
    unexpected status. Raises ``requests.RequestException`` if the webhook is unreachable.
    """
    resp = requests.post(f"{base_url}/jobs/claim", json={"worker_id": worker_name}, timeout=30)

    if resp.status_code == 204:
        return None

    if not resp.ok:
        logger.error(
            f"unexpected claim response {resp.status_code}: {resp.text}",
            extra={"worker_id": worker_name},
        )
        return None

    return resp.json()


def _report(base_url: str, job_id: int, worker_name: str, result: JobResult) -> None:
    log_extra = {"job_id": job_id, "worker_id": worker_name}

    logger.debug(f"reporting job {job_id} as {result.action}", extra=log_extra)

    if result.action == "complete":
        _post(
            f"{base_url}/jobs/{job_id}/complete",
            {"worker_id": worker_name, "filename": result.filename},
            log_extra,
        )
    elif result.action == "skip":
        # a skip drops the job with no rescan/notification
        _post(f"{base_url}/jobs/{job_id}/complete", {"worker_id": worker_name}, log_extra)
    elif result.action == "retry":
        _post(
            f"{base_url}/jobs/{job_id}/fail",
            {"worker_id": worker_name, "retry": True, "reason": result.reason},
            log_extra,
        )
    else:  # fail
        _post(
            f"{base_url}/jobs/{job_id}/fail",
            {
                "worker_id": worker_name,
                "retry": False,
                "reason": result.reason,
                "log_tail": result.log_tail,
            },
            log_extra,
        )


def run() -> None:
    base_url = config.worker.webhook_url.rstrip("/")
    worker_name = config.worker.worker_name
    poll_interval = config.worker.poll_interval
    heartbeat_interval = config.worker.heartbeat_interval

    transcoder = Transcoder()

    worker_extra = {"worker_id": worker_name}

    logger.info(f"worker {worker_name!r} polling {base_url} for transcode jobs", extra=worker_extra)

    while True:
        try:
            job = _claim(base_url, worker_name)
        except requests.RequestException:
            logger.warning(
                "failed to reach webhook to claim a job, will retry",
                exc_info=True,
                extra=worker_extra,
            )
            time.sleep(poll_interval)
            continue

        if job is None:
            time.sleep(poll_interval)
            continue

        job_id = job["id"]
        job_extra = {"job_id": job_id, "worker_id": worker_name}

        logger.info(f"claimed job {job_id}: {job['path']}", extra=job_extra)

        started = time.monotonic()
        try:
            with _Heartbeat(base_url, job_id, worker_name, heartbeat_interval):
                result = transcoder.transcode(
                    job["path"], job["quality_profile"], job.get("original_language")
                )
        except Exception:
            logger.warning(
                f"unhandled error on job {job_id}, will retry", exc_info=True, extra=job_extra
            )
            result = JobResult("retry", reason="unhandled worker error")

        elapsed = time.monotonic() - started
        detail = f" ({result.reason})" if result.reason else ""
        logger.info(
            f"job {job_id} finished in {elapsed:.1f}s: {result.action}{detail}", extra=job_extra
        )

        _report(base_url, job_id, worker_name, result)

        time.sleep(poll_interval)
