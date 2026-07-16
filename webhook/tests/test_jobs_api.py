from collections.abc import Iterator
from unittest.mock import patch

import pytest
from flask.testing import FlaskClient

import wi1_bot.webhook.app as app_mod
from wi1_bot.webhook.config import config
from wi1_bot.webhook.transcode_queue import queue


@pytest.fixture
def client(db: None) -> Iterator[FlaskClient]:
    queue.clear()
    yield app_mod.app.test_client()


def test_health(client: FlaskClient) -> None:
    assert client.get("/health").status_code == 200


def test_claim_empty_returns_204(client: FlaskClient) -> None:
    assert client.post("/jobs/claim", json={"worker_id": "w"}).status_code == 204


def test_full_success_lifecycle(client: FlaskClient) -> None:
    queue.add("/movies/a.mkv", "good", "English")

    resp = client.post("/jobs/claim", json={"worker_id": "w"})
    assert resp.status_code == 200
    job = resp.get_json()
    assert job["path"] == "/movies/a.mkv"
    assert job["quality_profile"] == "good"
    assert job["original_language"] == "English"
    assert job["heartbeat"] == config.webhook.heartbeat

    with patch.object(app_mod, "rescan_content") as mock_rescan:
        resp = client.post(f"/jobs/{job['id']}/complete", json={"filename": "a-TRANSCODED.mkv"})

    assert resp.status_code == 200
    mock_rescan.assert_called_once()
    assert queue.size == 0


def test_skip_drops_without_rescan(client: FlaskClient) -> None:
    queue.add("/movies/a.mkv", "good")
    job = client.post("/jobs/claim", json={"worker_id": "w"}).get_json()

    with patch.object(app_mod, "rescan_content") as mock_rescan:
        # no filename -> the worker skipped the job
        resp = client.post(f"/jobs/{job['id']}/complete", json={})

    assert resp.status_code == 200
    mock_rescan.assert_not_called()
    assert queue.size == 0


def test_fail_terminal_notifies_and_drops(client: FlaskClient) -> None:
    queue.add("/movies/a.mkv", "good")
    job = client.post("/jobs/claim", json={"worker_id": "w"}).get_json()

    with patch.object(app_mod, "push") as mock_push:
        resp = client.post(f"/jobs/{job['id']}/fail", json={"retry": False, "reason": "boom"})

    assert resp.status_code == 200
    mock_push.send.assert_called_once()
    assert queue.size == 0


def test_fail_retry_requeues_without_notifying(client: FlaskClient) -> None:
    queue.add("/movies/a.mkv", "good")
    job = client.post("/jobs/claim", json={"worker_id": "w"}).get_json()

    with patch.object(app_mod, "push") as mock_push:
        resp = client.post(f"/jobs/{job['id']}/fail", json={"retry": True, "reason": "retry"})

    assert resp.status_code == 200
    mock_push.send.assert_not_called()
    assert queue.size == 1


def test_complete_unknown_job_returns_404(client: FlaskClient) -> None:
    resp = client.post("/jobs/999/complete", json={"worker_id": "w", "filename": "a.mkv"})
    assert resp.status_code == 404


def test_heartbeat(client: FlaskClient) -> None:
    queue.add("/movies/a.mkv", "good")
    job = client.post("/jobs/claim", json={"worker_id": "w"}).get_json()

    assert client.post(f"/jobs/{job['id']}/heartbeat", json={"worker_id": "w"}).status_code == 200
    assert (
        client.post(f"/jobs/{job['id']}/heartbeat", json={"worker_id": "other"}).status_code == 409
    )
