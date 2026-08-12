from threading import Event
from typing import cast
from unittest.mock import MagicMock

import pytest
from prometheus_client import REGISTRY

from wi1_bot.arr import ArrQueueItem, ArrQueueItemNotFound, Radarr, ReleaseProtocol, Sonarr
from wi1_bot.webhook.autobrr import ArrTarget, TargetName
from wi1_bot.webhook.queue_cleanup import ArrQueueCleanupWorker


def _target(name: str = "radarr") -> tuple[ArrTarget, MagicMock]:
    client = MagicMock()
    target = ArrTarget(
        cast(TargetName, name),
        "radarr" if name.startswith("radarr") else "sonarr",
        cast(Radarr | Sonarr, client),
    )
    return target, client


def _item(
    protocol: ReleaseProtocol = "usenet",
    *,
    downgrade: bool = True,
    tracked_download_state: str = "importBlocked",
) -> ArrQueueItem:
    message = (
        "Not a Custom Format upgrade for existing movie file(s). New: [] (10)"
        if downgrade
        else "Not an upgrade for existing movie file"
    )
    return ArrQueueItem.model_validate(
        {
            "id": 7,
            "title": "Movie.2026.E2ELOW",
            "protocol": protocol,
            "status": "completed",
            "trackedDownloadStatus": "warning",
            "trackedDownloadState": tracked_download_state,
            "statusMessages": [{"title": "Movie.mkv", "messages": [message]}],
        }
    )


def _sample(name: str, labels: dict[str, str]) -> float:
    value = REGISTRY.get_sample_value(name, labels)
    return value if value is not None else 0


@pytest.mark.parametrize(
    ("protocol", "remove_from_client", "outcome"),
    [("torrent", False, "ignored"), ("usenet", True, "removed")],
)
def test_cleanup_uses_protocol_specific_removal_policy(
    protocol: ReleaseProtocol,
    remove_from_client: bool,
    outcome: str,
) -> None:
    target, client = _target()
    client.get_queue_items.return_value = [_item(protocol)]
    labels = {"target": "radarr", "protocol": protocol, "outcome": outcome}
    before = _sample("wi1_bot_webhook_queue_cleanup_items_total", labels)

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_called_once_with(7, remove_from_client=remove_from_client)
    assert _sample("wi1_bot_webhook_queue_cleanup_items_total", labels) == before + 1


def test_cleanup_preserves_unrelated_manual_interaction_items() -> None:
    target, client = _target()
    client.get_queue_items.return_value = [_item(downgrade=False)]

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_not_called()


def test_cleanup_removes_pending_custom_format_downgrade() -> None:
    target, client = _target("sonarr")
    client.get_queue_items.return_value = [_item(tracked_download_state="importPending")]

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_called_once_with(7, remove_from_client=True)


def test_cleanup_isolates_item_failures_and_not_found_races() -> None:
    target, client = _target("sonarr4k")
    first = _item().model_copy(update={"id": 1})
    second = _item().model_copy(update={"id": 2})
    third = _item().model_copy(update={"id": 3})
    client.get_queue_items.return_value = [first, second, third]
    client.remove_queue_item.side_effect = [
        ArrQueueItemNotFound(1),
        RuntimeError("unavailable"),
        None,
    ]

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    assert client.remove_queue_item.call_count == 3
    client.remove_queue_item.assert_any_call(3, remove_from_client=True)


def test_cleanup_isolates_target_poll_failures() -> None:
    failed_target, failed_client = _target("radarr")
    healthy_target, healthy_client = _target("sonarr")
    failed_client.get_queue_items.side_effect = RuntimeError("unavailable")
    healthy_client.get_queue_items.return_value = [_item()]

    ArrQueueCleanupWorker([failed_target, healthy_target], poll_interval=60).run_once()

    healthy_client.remove_queue_item.assert_called_once_with(7, remove_from_client=True)


def test_worker_scans_immediately_and_stops_cleanly() -> None:
    target, client = _target()
    scanned = Event()
    client.get_queue_items.side_effect = lambda: scanned.set() or []
    worker = ArrQueueCleanupWorker([target], poll_interval=3600)

    worker.start()
    assert scanned.wait(timeout=2)
    worker.stop()

    assert client.get_queue_items.call_count == 1
