import threading
import time
from typing import Any

import requests
import structlog
from structlog.contextvars import bound_contextvars

from wi1_bot.transcoder.config import config
from wi1_bot.transcoder.transcoder import JobResult, Transcoder

logger = structlog.get_logger(__name__)


class _Heartbeat:
    """Periodically extends a claimed job's lease while it is being transcoded.

    A transcode can outlive the webhook's lease; heartbeats keep the lease alive so
    the job isn't re-dispatched to another worker mid-transcode. If this worker
    crashes, heartbeats stop and the lease expires, letting the webhook reclaim it.
    """

    def __init__(self, base_url: str, job_id: int, worker_name: str, interval: float) -> None:
        self._url = f"{base_url}/jobs/{job_id}/heartbeat"
        self._job_id = job_id
        self._worker_name = worker_name
        self._payload = {"worker_id": worker_name}
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        with bound_contextvars(job_id=self._job_id, worker_id=self._worker_name):
            while not self._stop.wait(self._interval):
                logger.debug("sending heartbeat")

                try:
                    resp = requests.post(self._url, json=self._payload, timeout=30)
                except requests.RequestException:
                    logger.warning(
                        "heartbeat failed to send",
                        exc_info=True,
                    )
                    continue

                if resp.status_code == 409:
                    # the webhook no longer thinks we hold the lease; the job may have been
                    # reclaimed and re-dispatched to another worker while we keep transcoding
                    logger.warning("heartbeat rejected because lease was lost")
                elif not resp.ok:
                    logger.error(
                        "heartbeat received unexpected response",
                        status_code=resp.status_code,
                    )
                else:
                    logger.debug("heartbeat accepted")

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()


def _post(url: str, payload: dict[str, Any]) -> None:
    try:
        resp = requests.post(url, json=payload, timeout=30)
    except requests.RequestException:
        # if the report doesn't land, the lease will expire and the job is re-dispatched
        logger.warning(
            "failed to report job outcome; lease will expire",
            url=url,
            exc_info=True,
        )
        return

    if not resp.ok:
        logger.warning(
            "webhook returned unsuccessful response",
            url=url,
            status_code=resp.status_code,
            response=resp.text,
        )
    else:
        logger.debug("job outcome reported", url=url, status_code=resp.status_code)


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
            "unexpected job claim response",
            status_code=resp.status_code,
            response=resp.text,
        )
        return None

    return resp.json()


def _report(base_url: str, job_id: int, worker_name: str, result: JobResult) -> None:
    logger.debug("reporting job outcome", action=result.action)

    if result.action == "complete":
        _post(
            f"{base_url}/jobs/{job_id}/complete",
            {"worker_id": worker_name, "filename": result.filename},
        )
    elif result.action == "skip":
        # a skip drops the job with no rescan/notification
        _post(f"{base_url}/jobs/{job_id}/complete", {"worker_id": worker_name})
    elif result.action == "retry":
        _post(
            f"{base_url}/jobs/{job_id}/fail",
            {"worker_id": worker_name, "retry": True, "reason": result.reason},
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
        )


def run() -> None:
    base_url = config.worker.webhook_url.rstrip("/")
    worker_name = config.worker.worker_name
    poll_interval = config.worker.poll_interval

    transcoder = Transcoder()

    with bound_contextvars(worker_id=worker_name):
        logger.info("polling for transcode jobs", base_url=base_url)

        while True:
            try:
                job = _claim(base_url, worker_name)
            except requests.RequestException:
                logger.warning(
                    "failed to reach webhook to claim a job, will retry",
                    exc_info=True,
                )
                time.sleep(poll_interval)
                continue

            if job is None:
                time.sleep(poll_interval)
                continue

            job_id = job["id"]

            with bound_contextvars(job_id=job_id):
                logger.info("transcode job claimed", path=job["path"])

                started = time.monotonic()
                try:
                    # the webhook owns the cadence and tells us how often to heartbeat
                    with _Heartbeat(base_url, job_id, worker_name, job["heartbeat"]):
                        result = transcoder.transcode(
                            job["path"], job["quality_profile"], job.get("original_language")
                        )
                except Exception:
                    logger.warning("unhandled job error; will retry", exc_info=True)
                    result = JobResult("retry", reason="unhandled worker error")

                elapsed = time.monotonic() - started
                logger.info(
                    "transcode job finished",
                    elapsed_seconds=round(elapsed, 1),
                    action=result.action,
                    reason=result.reason,
                )

                _report(base_url, job_id, worker_name, result)

            time.sleep(poll_interval)
