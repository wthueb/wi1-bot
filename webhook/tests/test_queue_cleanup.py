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
    client.get_download_origin.return_value = "automatic"
    target = ArrTarget(
        cast(TargetName, name),
        "radarr" if name.startswith("radarr") else "sonarr",
        cast(Radarr | Sonarr, client),
    )
    return target, client


def _item(
    protocol: ReleaseProtocol = "usenet",
    *,
    tracked_download_state: str = "importBlocked",
    message: str = "Not a Custom Format upgrade for existing movie file(s). New: [] (10)",
) -> ArrQueueItem:
    return ArrQueueItem.model_validate(
        {
            "id": 7,
            "downloadId": "download-7",
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


@pytest.mark.parametrize("target_name", ["radarr", "radarr4k", "sonarr", "sonarr4k"])
@pytest.mark.parametrize("tracked_download_state", ["importBlocked", "importPending"])
@pytest.mark.parametrize(
    "message",
    [
        "Not a Custom Format upgrade for existing movie file(s). New: [] (10)",
        "Not an upgrade for existing episode file(s). "
        "Existing quality: WEBDL-2160p. New Quality WEBDL-1080p.",
        "Not a quality revision upgrade for existing episode file(s)",
        "Not a quality revision upgrade for existing movie file(s)",
    ],
)
@pytest.mark.parametrize(
    ("protocol", "remove_from_client", "outcome"),
    [("torrent", False, "ignored"), ("usenet", True, "removed")],
)
def test_cleanup_uses_protocol_specific_removal_policy(
    protocol: ReleaseProtocol,
    remove_from_client: bool,
    outcome: str,
    message: str,
    tracked_download_state: str,
    target_name: str,
) -> None:
    target, client = _target(target_name)
    client.get_queue_items.return_value = [
        _item(
            protocol,
            message=message,
            tracked_download_state=tracked_download_state,
        )
    ]
    labels = {"target": target_name, "protocol": protocol, "outcome": outcome}
    before = _sample("wi1_bot_webhook_queue_cleanup_items_total", labels)

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_called_once_with(7, remove_from_client=remove_from_client)
    assert _sample("wi1_bot_webhook_queue_cleanup_items_total", labels) == before + 1


def test_cleanup_preserves_unrelated_manual_interaction_items() -> None:
    target, client = _target()
    client.get_queue_items.return_value = [_item(message="Not enough free space")]

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_not_called()
    client.get_download_origin.assert_not_called()


@pytest.mark.parametrize("target_name", ["radarr", "radarr4k", "sonarr", "sonarr4k"])
@pytest.mark.parametrize("protocol", ["torrent", "usenet"])
@pytest.mark.parametrize("origin", ["manual", "unknown"])
def test_cleanup_preserves_protected_origins(
    target_name: str, protocol: ReleaseProtocol, origin: str
) -> None:
    target, client = _target(target_name)
    client.get_queue_items.return_value = [_item(protocol)]
    client.get_download_origin.return_value = origin
    labels = {"target": target_name, "protocol": protocol, "outcome": f"skipped_{origin}"}
    before = _sample("wi1_bot_webhook_queue_cleanup_items_total", labels)

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_not_called()
    client.get_download_origin.assert_called_once_with("download-7")
    assert _sample("wi1_bot_webhook_queue_cleanup_items_total", labels) == before + 1


@pytest.mark.parametrize("target_name", ["radarr", "radarr4k", "sonarr", "sonarr4k"])
@pytest.mark.parametrize("protocol", ["torrent", "usenet"])
@pytest.mark.parametrize("download_id", [None, "", " ", "download-7"])
def test_manual_override_bypasses_origin_check(
    target_name: str, protocol: ReleaseProtocol, download_id: str | None
) -> None:
    target, client = _target(target_name)
    client.get_queue_items.return_value = [
        _item(protocol).model_copy(update={"download_id": download_id})
    ]
    client.get_download_origin.side_effect = RuntimeError("must not be called")

    ArrQueueCleanupWorker([target], poll_interval=60, manually_added=True).run_once()

    client.remove_queue_item.assert_called_once_with(7, remove_from_client=protocol == "usenet")
    client.get_download_origin.assert_not_called()


@pytest.mark.parametrize("protocol", ["torrent", "usenet"])
@pytest.mark.parametrize("download_id", [None, "", " ", "\t"])
def test_missing_download_id_is_protected(
    protocol: ReleaseProtocol, download_id: str | None
) -> None:
    target, client = _target()
    client.get_queue_items.return_value = [
        _item(protocol).model_copy(update={"download_id": download_id})
    ]
    labels = {"target": "radarr", "protocol": protocol, "outcome": "skipped_unknown"}
    before = _sample("wi1_bot_webhook_queue_cleanup_items_total", labels)

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_not_called()
    client.get_download_origin.assert_not_called()
    assert _sample("wi1_bot_webhook_queue_cleanup_items_total", labels) == before + 1


@pytest.mark.parametrize("protocol", ["torrent", "usenet"])
def test_origin_failure_is_cached_and_isolated(protocol: ReleaseProtocol) -> None:
    target, client = _target()
    client.get_queue_items.return_value = [
        _item(protocol).model_copy(update={"id": 1}),
        _item(protocol).model_copy(update={"id": 2}),
        _item(protocol).model_copy(update={"id": 3, "download_id": "other-download"}),
    ]
    client.get_download_origin.side_effect = [RuntimeError("unavailable"), "automatic"]
    labels = {"target": "radarr", "protocol": protocol, "outcome": "origin_error"}
    before = _sample("wi1_bot_webhook_queue_cleanup_items_total", labels)

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    assert client.get_download_origin.call_count == 2
    client.remove_queue_item.assert_called_once_with(3, remove_from_client=protocol == "usenet")
    assert _sample("wi1_bot_webhook_queue_cleanup_items_total", labels) == before + 2


@pytest.mark.parametrize("origin", ["automatic", "manual", "unknown"])
def test_origin_cache_is_refreshed_between_scans(origin: str) -> None:
    target, client = _target("sonarr")
    client.get_queue_items.return_value = [
        _item().model_copy(update={"id": 1}),
        _item().model_copy(update={"id": 2}),
    ]
    client.get_download_origin.side_effect = [origin, "automatic"]
    worker = ArrQueueCleanupWorker([target], poll_interval=60)

    worker.run_once()
    assert client.get_download_origin.call_count == 1
    assert client.remove_queue_item.call_count == (2 if origin == "automatic" else 0)
    client.remove_queue_item.reset_mock()
    worker.run_once()

    assert client.get_download_origin.call_count == 2
    assert client.remove_queue_item.call_count == 2


def test_origin_cache_is_scoped_to_target() -> None:
    protected_target, protected_client = _target("radarr")
    automatic_target, automatic_client = _target("sonarr")
    protected_client.get_queue_items.return_value = [_item()]
    automatic_client.get_queue_items.return_value = [_item()]
    protected_client.get_download_origin.return_value = "manual"

    ArrQueueCleanupWorker([protected_target, automatic_target], poll_interval=60).run_once()

    protected_client.remove_queue_item.assert_not_called()
    automatic_client.get_download_origin.assert_called_once_with("download-7")
    automatic_client.remove_queue_item.assert_called_once_with(7, remove_from_client=True)


def test_cleanup_removes_pending_custom_format_downgrade() -> None:
    target, client = _target("sonarr")
    client.get_queue_items.return_value = [_item(tracked_download_state="importPending")]

    ArrQueueCleanupWorker([target], poll_interval=60).run_once()

    client.remove_queue_item.assert_called_once_with(7, remove_from_client=True)


def test_cleanup_isolates_item_failures_and_not_found_races() -> None:
    target, client = _target("sonarr4k")
    first = _item().model_copy(update={"id": 1, "download_id": "download-1"})
    second = _item().model_copy(update={"id": 2, "download_id": "download-2"})
    third = _item().model_copy(update={"id": 3, "download_id": "download-3"})
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
