"""End-to-end interaction tests between the transcoder worker and the webhook.

These wire the worker's HTTP client (``wi1_bot.transcoder.worker.requests``) straight
into the webhook's Flask test client, so a claim/heartbeat/complete/fail issued by real
worker code drives the real webhook endpoints, queue, and SQLite database.
"""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from urllib.parse import urlsplit

import pytest
import requests
from flask.testing import FlaskClient
from sqlalchemy.orm import Session
from werkzeug.test import TestResponse

import wi1_bot.transcoder.worker as worker_mod
import wi1_bot.webhook.app as app_mod
from wi1_bot.transcoder.transcoder import JobResult
from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_engine
from wi1_bot.webhook.models import TranscodeItem
from wi1_bot.webhook.transcode_queue import _utcnow, queue

BASE = "http://webhook"


class _ClientResponse:
    """Adapts a Flask ``TestResponse`` to the slice of ``requests.Response`` the worker uses."""

    def __init__(self, tr: TestResponse) -> None:
        self._tr = tr
        self.status_code = tr.status_code
        self.text = tr.get_data(as_text=True)

    @property
    def ok(self) -> bool:
        return self.status_code < 400

    def json(self) -> Any:
        return self._tr.get_json()


class _ClientRequests:
    """Stands in for the ``requests`` module inside the worker, routing posts to a test client."""

    RequestException = requests.RequestException

    def __init__(self, client: FlaskClient) -> None:
        self._client = client

    def post(self, url: str, json: Any = None, timeout: Any = None) -> _ClientResponse:
        return _ClientResponse(self._client.post(urlsplit(url).path, json=json))


@pytest.fixture
def wired(db: None) -> Iterator[FlaskClient]:
    """Webhook test client with the transcoder worker's HTTP calls routed into it."""
    queue.clear()
    client = app_mod.app.test_client()
    with patch.object(worker_mod, "requests", _ClientRequests(client)):
        yield client


def _db_item(job_id: int) -> TranscodeItem:
    with Session(get_engine()) as session:
        item = session.get(TranscodeItem, job_id)
        assert item is not None
        return item


def _expire_lease(job_id: int) -> None:
    with Session(get_engine()) as session:
        item = session.get(TranscodeItem, job_id)
        assert item is not None
        item.lease_expires_at = _utcnow() - timedelta(seconds=1)
        session.commit()


# --- enqueue -> claim ------------------------------------------------------------------


def test_claim_returns_none_when_queue_empty(wired: FlaskClient) -> None:
    assert worker_mod._claim(BASE, "w1") is None


def test_enqueue_then_claim_hands_off_full_job(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good", "English")

    job = worker_mod._claim(BASE, "w1")

    assert job is not None
    assert job["id"] == job_id
    assert job["path"] == "/movies/a.mkv"
    assert job["quality_profile"] == "good"
    assert job["original_language"] == "English"
    # claiming marks it in_progress owned by this worker
    assert _db_item(job_id).worker_id == "w1"


def test_claim_is_fifo_across_workers(wired: FlaskClient) -> None:
    queue.add("/movies/a.mkv", "good")
    queue.add("/movies/b.mkv", "good")

    first = worker_mod._claim(BASE, "w1")
    second = worker_mod._claim(BASE, "w2")

    assert first is not None and second is not None
    assert first["path"] == "/movies/a.mkv"
    assert second["path"] == "/movies/b.mkv"
    assert worker_mod._claim(BASE, "w3") is None


# --- claim -> complete / skip / fail / retry -------------------------------------------


def test_complete_lifecycle_triggers_rescan_and_drains_queue(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good", "English")
    assert worker_mod._claim(BASE, "w1") is not None

    with patch.object(app_mod, "rescan_content") as mock_rescan:
        worker_mod._report(BASE, job_id, "w1", JobResult("complete", filename="a-TRANSCODED.mkv"))

    mock_rescan.assert_called_once()
    assert queue.size == 0


def test_skip_completes_without_rescan(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert worker_mod._claim(BASE, "w1") is not None

    with patch.object(app_mod, "rescan_content") as mock_rescan:
        worker_mod._report(BASE, job_id, "w1", JobResult("skip"))

    mock_rescan.assert_not_called()
    assert queue.size == 0


def test_terminal_fail_notifies_and_drops(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert worker_mod._claim(BASE, "w1") is not None

    with patch.object(app_mod, "push") as mock_push:
        worker_mod._report(
            BASE, job_id, "w1", JobResult("fail", reason="boom", log_tail="ffmpeg died")
        )

    mock_push.send.assert_called_once()
    assert queue.size == 0


def test_retry_requeues_and_is_reclaimed_by_another_worker(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert worker_mod._claim(BASE, "w1") is not None

    with patch.object(app_mod, "push") as mock_push:
        worker_mod._report(BASE, job_id, "w1", JobResult("retry", reason="interrupted"))

    # a retry requeues (no notification) rather than dropping the job
    mock_push.send.assert_not_called()
    assert queue.size == 1

    reclaimed = worker_mod._claim(BASE, "w2")
    assert reclaimed is not None
    assert reclaimed["id"] == job_id
    assert _db_item(job_id).worker_id == "w2"
    assert _db_item(job_id).attempts == 2


def test_complete_for_unknown_job_is_a_noop(wired: FlaskClient) -> None:
    # nothing enqueued: a completion for a stale/expired id must not raise or rescan
    with patch.object(app_mod, "rescan_content") as mock_rescan:
        worker_mod._report(BASE, 999, "w1", JobResult("complete", filename="x.mkv"))

    mock_rescan.assert_not_called()
    assert queue.size == 0


# --- heartbeats ------------------------------------------------------------------------


def test_heartbeat_from_owner_renews_lease(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert worker_mod._claim(BASE, "w1") is not None
    _expire_lease(job_id)

    resp = worker_mod.requests.post(f"{BASE}/jobs/{job_id}/heartbeat", json={"worker_id": "w1"})

    assert resp.status_code == 200
    # the lease was pushed back into the future
    renewed = _db_item(job_id).lease_expires_at
    assert renewed is not None
    assert renewed > _utcnow()


def test_heartbeat_from_wrong_worker_is_rejected(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert worker_mod._claim(BASE, "w1") is not None

    resp = worker_mod.requests.post(f"{BASE}/jobs/{job_id}/heartbeat", json={"worker_id": "w2"})

    assert resp.status_code == 409


def test_heartbeat_rejected_after_lease_reclaimed(wired: FlaskClient) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert worker_mod._claim(BASE, "w1") is not None

    # w1 stalls, its lease expires, and w2 reclaims the job
    _expire_lease(job_id)
    assert worker_mod._claim(BASE, "w2") is not None

    # w1's now-stale heartbeat must be rejected (it no longer owns the lease)
    resp = worker_mod.requests.post(f"{BASE}/jobs/{job_id}/heartbeat", json={"worker_id": "w1"})
    assert resp.status_code == 409


# --- configurable lease ----------------------------------------------------------------


def test_claim_uses_configured_lease(wired: FlaskClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config.webhook, "lease_secs", 123)

    job_id = queue.add("/movies/a.mkv", "good")
    before = _utcnow()
    assert worker_mod._claim(BASE, "w1") is not None

    lease = _db_item(job_id).lease_expires_at
    assert lease is not None
    # lease should be ~123s out; allow a few seconds of slack for test execution
    assert timedelta(seconds=120) <= lease - before <= timedelta(seconds=130)
