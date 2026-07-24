from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import MagicMock, patch

import pytest
from flask.testing import FlaskClient
from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY
from sqlalchemy.orm import Session

import wi1_bot.webhook.app as app_mod
import wi1_bot.webhook.metrics as metrics_mod
import wi1_bot.webhook.rescan as rescan_mod
from wi1_bot.arr.common import ImportMode
from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_engine
from wi1_bot.webhook.models import TranscodeItem
from wi1_bot.webhook.transcode_queue import _utcnow, queue


@pytest.fixture
def client(db: None) -> Iterator[FlaskClient]:
    queue.clear()
    yield app_mod.app.test_client()


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return value if value is not None else 0


def test_metrics_endpoint_exposes_application_and_standard_metrics(client: FlaskClient) -> None:
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.content_type == CONTENT_TYPE_LATEST
    body = response.get_data(as_text=True)
    assert "wi1_bot_webhook_http_requests_total" in body
    assert "wi1_bot_webhook_queue_jobs" in body
    assert "wi1_bot_webhook_database_up 1.0" in body
    assert "wi1_bot_webhook_build_info" in body
    assert "python_info" in body
    assert "python_gc_objects_collected_total" in body


def test_http_metrics_use_normalized_flask_route(client: FlaskClient) -> None:
    labels = {
        "method": "POST",
        "route": "/jobs/<int:item_id>/heartbeat",
        "status_code": "409",
    }
    before = _sample("wi1_bot_webhook_http_requests_total", labels)

    response = client.post("/jobs/987654/heartbeat", json={"worker_id": "worker"})

    assert response.status_code == 409
    assert _sample("wi1_bot_webhook_http_requests_total", labels) == before + 1
    assert (
        _sample(
            "wi1_bot_webhook_http_request_duration_seconds_count",
            {"method": "POST", "route": "/jobs/<int:item_id>/heartbeat"},
        )
        >= 1
    )
    assert (
        _sample(
            "wi1_bot_webhook_http_requests_in_progress",
            {"method": "POST", "route": "/jobs/<int:item_id>/heartbeat"},
        )
        == 0
    )


def test_event_metrics_use_bounded_values(client: FlaskClient) -> None:
    invalid_labels = {"event_type": "invalid", "source": "unknown", "outcome": "invalid"}
    unsupported_labels = {
        "event_type": "unsupported",
        "source": "unknown",
        "outcome": "unsupported",
    }
    invalid_before = _sample("wi1_bot_webhook_events_total", invalid_labels)
    unsupported_before = _sample("wi1_bot_webhook_events_total", unsupported_labels)

    assert client.post("/", data="not json", content_type="application/json").status_code == 400
    assert client.post("/", json={"eventType": "UnexpectedUserValue"}).status_code == 200

    assert _sample("wi1_bot_webhook_events_total", invalid_labels) == invalid_before + 1
    assert _sample("wi1_bot_webhook_events_total", unsupported_labels) == unsupported_before + 1
    assert "UnexpectedUserValue" not in client.get("/metrics").get_data(as_text=True)


def test_event_metrics_record_enqueue_and_internal_failure(client: FlaskClient) -> None:
    labels = {
        "event_type": "download",
        "source": "radarr",
        "outcome": "enqueued",
    }
    failed_labels = {
        "event_type": "download",
        "source": "radarr",
        "outcome": "failed_internal",
    }
    before = _sample("wi1_bot_webhook_events_total", labels)
    failed_before = _sample("wi1_bot_webhook_events_total", failed_labels)
    event = {"eventType": "Download", "instanceName": config.radarr.instance_name, "movie": {}}

    with patch.object(app_mod, "on_download"):
        assert client.post("/", json=event).status_code == 200
    with patch.object(app_mod, "on_download", side_effect=RuntimeError("boom")):
        assert client.post("/", json=event).status_code == 200

    assert _sample("wi1_bot_webhook_events_total", labels) == before + 1
    assert _sample("wi1_bot_webhook_events_total", failed_labels) == failed_before + 1


def test_queue_gauges_report_status_age_and_expired_leases(client: FlaskClient) -> None:
    queued_id = queue.add("/movies/queued.mkv", "good")
    in_progress_id = queue.add("/movies/claimed.mkv", "good")
    claimed = queue.claim("worker")
    assert claimed is not None
    assert claimed.id == queued_id

    now = _utcnow()
    with Session(get_engine()) as session:
        queued = session.get(TranscodeItem, in_progress_id)
        in_progress = session.get(TranscodeItem, queued_id)
        assert queued is not None and in_progress is not None
        queued.status_changed_at = now - timedelta(seconds=20)
        in_progress.status_changed_at = now - timedelta(seconds=30)
        in_progress.lease_expires_at = now - timedelta(seconds=1)
        session.commit()

    assert client.get("/metrics").status_code == 200
    assert _sample("wi1_bot_webhook_queue_jobs", {"status": "queued"}) == 1
    assert _sample("wi1_bot_webhook_queue_jobs", {"status": "in_progress"}) == 1
    assert _sample("wi1_bot_webhook_queue_oldest_job_age_seconds", {"status": "queued"}) >= 20
    assert _sample("wi1_bot_webhook_queue_oldest_job_age_seconds", {"status": "in_progress"}) >= 30
    assert _sample("wi1_bot_webhook_queue_expired_leases", {}) == 1


def test_job_lifecycle_metrics_cover_claim_retry_expiry_and_skip(client: FlaskClient) -> None:
    claim_initial = {"kind": "initial"}
    claim_retry = {"kind": "retry"}
    claim_expired = {"kind": "expired_lease"}
    initial_before = _sample("wi1_bot_webhook_job_claims_total", claim_initial)
    retry_before = _sample("wi1_bot_webhook_job_claims_total", claim_retry)
    expired_before = _sample("wi1_bot_webhook_job_claims_total", claim_expired)
    requeued_before = _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "requeued"})
    lease_expired_before = _sample(
        "wi1_bot_webhook_job_attempts_total", {"outcome": "lease_expired"}
    )
    skipped_before = _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "skipped"})

    job_id = queue.add("/movies/a.mkv", "good")
    first_claim = client.post("/jobs/claim", json={"worker_id": "one"}).get_json()
    assert first_claim["id"] == job_id
    assert client.post(f"/jobs/{job_id}/fail", json={"retry": True}).status_code == 200
    assert client.post("/jobs/claim", json={"worker_id": "two"}).status_code == 200

    with Session(get_engine()) as session:
        item = session.get(TranscodeItem, job_id)
        assert item is not None
        item.lease_expires_at = _utcnow() - timedelta(seconds=1)
        session.commit()

    assert client.post("/jobs/claim", json={"worker_id": "three"}).status_code == 200
    assert client.post(f"/jobs/{job_id}/complete", json={}).status_code == 200

    assert _sample("wi1_bot_webhook_job_claims_total", claim_initial) == initial_before + 1
    assert _sample("wi1_bot_webhook_job_claims_total", claim_retry) == retry_before + 1
    assert _sample("wi1_bot_webhook_job_claims_total", claim_expired) == expired_before + 1
    assert (
        _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "requeued"})
        == requeued_before + 1
    )
    assert (
        _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "lease_expired"})
        == lease_expired_before + 1
    )
    assert (
        _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "skipped"}) == skipped_before + 1
    )
    assert (
        _sample(
            "wi1_bot_webhook_job_queue_wait_duration_seconds_count",
            {"kind": "initial"},
        )
        >= 1
    )
    assert (
        _sample(
            "wi1_bot_webhook_job_attempt_duration_seconds_count",
            {"outcome": "lease_expired"},
        )
        >= 1
    )


def test_job_lifecycle_metrics_cover_heartbeats_completion_and_terminal_failure(
    client: FlaskClient,
) -> None:
    accepted_before = _sample("wi1_bot_webhook_job_heartbeats_total", {"outcome": "accepted"})
    rejected_before = _sample("wi1_bot_webhook_job_heartbeats_total", {"outcome": "rejected"})
    completed_before = _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "completed"})
    terminal_before = _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "terminal_failure"})

    completed_id = queue.add("/movies/completed.mkv", "good")
    assert client.post("/jobs/claim", json={"worker_id": "one"}).status_code == 200
    assert (
        client.post(f"/jobs/{completed_id}/heartbeat", json={"worker_id": "one"}).status_code == 200
    )
    assert (
        client.post(f"/jobs/{completed_id}/heartbeat", json={"worker_id": "other"}).status_code
        == 409
    )
    with patch.object(app_mod, "rescan_content"):
        assert (
            client.post(
                f"/jobs/{completed_id}/complete",
                json={"worker_id": "one", "filename": "completed-new.mkv"},
            ).status_code
            == 200
        )

    failed_id = queue.add("/movies/failed.mkv", "good")
    assert client.post("/jobs/claim", json={"worker_id": "two"}).status_code == 200
    with patch.object(app_mod, "push"):
        assert (
            client.post(
                f"/jobs/{failed_id}/fail",
                json={"worker_id": "two", "retry": False, "reason": "failed"},
            ).status_code
            == 200
        )

    assert (
        _sample("wi1_bot_webhook_job_heartbeats_total", {"outcome": "accepted"})
        == accepted_before + 1
    )
    assert (
        _sample("wi1_bot_webhook_job_heartbeats_total", {"outcome": "rejected"})
        == rejected_before + 1
    )
    assert (
        _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "completed"})
        == completed_before + 1
    )
    assert (
        _sample("wi1_bot_webhook_job_attempts_total", {"outcome": "terminal_failure"})
        == terminal_before + 1
    )


def test_rescan_metrics_record_success_not_found_and_error() -> None:
    radarr = MagicMock()
    sonarr = MagicMock()
    radarr.get_movies.return_value = [{"id": 7, "path": "/movies/a"}]
    success_labels = {"target": "radarr", "outcome": "success"}
    not_found_labels = {"target": "sonarr", "outcome": "not_found"}
    error_labels = {"target": "radarr", "outcome": "error"}
    success_before = _sample("wi1_bot_webhook_rescan_operations_total", success_labels)
    not_found_before = _sample("wi1_bot_webhook_rescan_operations_total", not_found_labels)
    error_before = _sample("wi1_bot_webhook_rescan_operations_total", error_labels)

    with patch.object(rescan_mod, "sleep"):
        rescan_mod.rescan_content(
            radarr,
            sonarr,
            config.radarr.root_folder,
            config.sonarr.root_folder,
            config.radarr.root_folder / "a" / "movie.mkv",
        )

    sonarr.get_series.return_value = []
    rescan_mod.rescan_content(
        radarr,
        sonarr,
        config.radarr.root_folder,
        config.sonarr.root_folder,
        config.sonarr.root_folder / "missing" / "episode.mkv",
    )

    radarr.get_movies.side_effect = RuntimeError("arr unavailable")
    with pytest.raises(RuntimeError, match="arr unavailable"):
        rescan_mod.rescan_content(
            radarr,
            sonarr,
            config.radarr.root_folder,
            config.sonarr.root_folder,
            config.radarr.root_folder / "a" / "movie.mkv",
        )

    assert _sample("wi1_bot_webhook_rescan_operations_total", success_labels) == success_before + 1
    assert (
        _sample("wi1_bot_webhook_rescan_operations_total", not_found_labels) == not_found_before + 1
    )
    assert _sample("wi1_bot_webhook_rescan_operations_total", error_labels) == error_before + 1
    assert _sample("wi1_bot_webhook_rescan_duration_seconds_count", {"target": "radarr"}) >= 2


@pytest.mark.parametrize(
    ("monitored", "outcome"),
    [(True, "triggered"), (False, "not_monitored")],
)
def test_cross_scan_metrics_use_bounded_outcomes(monitored: bool, outcome: str) -> None:
    movie_request = {
        "eventType": "Download",
        "instanceName": "Radarr",
        "movie": {"id": 1, "folderPath": "/movies/a"},
        "movieFile": {"relativePath": "a.mkv"},
    }
    mock_radarr = MagicMock()
    mock_radarr.get_movie_by_id.return_value = {"qualityProfileId": 1, "tmdbId": 42}
    mock_radarr.get_quality_profile_name.return_value = "good"
    mock_radarr.is_movie_monitored.return_value = monitored
    mock_config = MagicMock()
    mock_config.radarr.instance_name = "Radarr"
    mock_config.sonarr4k = None
    labels = {"target": "radarr4k", "outcome": outcome}
    before = _sample("wi1_bot_webhook_cross_scan_operations_total", labels)

    with (
        patch.object(app_mod, "instances", [mock_config.radarr]),
        patch.object(app_mod, "config", mock_config),
        patch.object(app_mod, "queue"),
        patch.object(app_mod, "Radarr") as mock_radarr_cls,
    ):
        mock_radarr_cls.from_config.return_value = mock_radarr
        app_mod.on_download(movie_request)

    assert _sample("wi1_bot_webhook_cross_scan_operations_total", labels) == before + 1
    if monitored:
        mock_radarr.downloaded_movies_scan.assert_called_once_with(
            config.radarr.root_folder / "a" / "a.mkv",
            import_mode=ImportMode.COPY,
        )
    else:
        mock_radarr.downloaded_movies_scan.assert_not_called()


def test_database_metric_reports_query_failure(client: FlaskClient) -> None:
    with patch.object(metrics_mod, "get_engine", side_effect=RuntimeError("database unavailable")):
        body = client.get("/metrics").get_data(as_text=True)

    assert "wi1_bot_webhook_database_up 0.0" in body
