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
        self._payload = {"worker_id": worker_name}
        self._interval = interval
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                requests.post(self._url, json=self._payload, timeout=30)
            except requests.RequestException:
                logger.debug("heartbeat request failed", exc_info=True)

    def __enter__(self) -> "_Heartbeat":
        self._thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self._stop.set()


def _post(url: str, payload: dict[str, Any]) -> None:
    try:
        requests.post(url, json=payload, timeout=30)
    except requests.RequestException:
        # if the report doesn't land, the lease will expire and the job is re-dispatched
        logger.warning(f"failed to report job outcome to {url}, lease will expire", exc_info=True)


def _report(base_url: str, job_id: int, result: JobResult) -> None:
    if result.action == "complete":
        _post(f"{base_url}/jobs/{job_id}/complete", {"filename": result.filename})
    elif result.action == "skip":
        # a skip drops the job with no rescan/notification
        _post(f"{base_url}/jobs/{job_id}/complete", {})
    elif result.action == "retry":
        _post(f"{base_url}/jobs/{job_id}/fail", {"retry": True, "reason": result.reason})
    else:  # fail
        _post(
            f"{base_url}/jobs/{job_id}/fail",
            {"retry": False, "reason": result.reason, "log_tail": result.log_tail},
        )


def run() -> None:
    base_url = config.worker.webhook_url.rstrip("/")
    worker_name = config.worker.worker_name
    poll_interval = config.worker.poll_interval
    heartbeat_interval = config.worker.heartbeat_interval

    transcoder = Transcoder()

    logger.info(f"worker {worker_name!r} polling {base_url} for transcode jobs")

    while True:
        try:
            resp = requests.post(
                f"{base_url}/jobs/claim", json={"worker_id": worker_name}, timeout=30
            )
        except requests.RequestException:
            logger.warning("failed to reach webhook to claim a job, will retry", exc_info=True)
            time.sleep(poll_interval)
            continue

        if resp.status_code == 204:
            time.sleep(poll_interval)
            continue

        if not resp.ok:
            logger.warning(f"unexpected claim response {resp.status_code}: {resp.text}")
            time.sleep(poll_interval)
            continue

        job = resp.json()
        job_id = job["id"]

        logger.info(f"claimed job {job_id}: {job['path']}")

        try:
            with _Heartbeat(base_url, job_id, worker_name, heartbeat_interval):
                result = transcoder.transcode(
                    job["path"], job["quality_profile"], job.get("original_language")
                )
        except Exception:
            logger.warning(f"unhandled error on job {job_id}, will retry", exc_info=True)
            result = JobResult("retry", reason="unhandled worker error")

        _report(base_url, job_id, result)

        time.sleep(poll_interval)
