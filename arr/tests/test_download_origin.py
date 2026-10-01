from typing import cast
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from wi1_bot.arr import ArrQueueItem, Radarr, Sonarr


@pytest.fixture(params=[Radarr, Sonarr])
def client(request: pytest.FixtureRequest) -> Radarr | Sonarr:
    client_type: type[Radarr] | type[Sonarr] = request.param
    return client_type("http://localhost:7878", "fake-api-key")


def _handler(client: Radarr | Sonarr) -> MagicMock:
    api = client._radarr if isinstance(client, Radarr) else client._sonarr
    return cast(MagicMock, api.history.handler)


def _record(**overrides: object) -> dict[str, object]:
    record: dict[str, object] = {
        "downloadId": "download-7",
        "eventType": "grabbed",
        "data": {"releaseSource": "Rss"},
        "ignoredUpstreamField": True,
    }
    record.update(overrides)
    return record


@pytest.mark.parametrize(
    ("source", "origin"),
    [
        ("Rss", "automatic"),
        ("Search", "automatic"),
        ("UserInvokedSearch", "automatic"),
        ("ReleasePush", "automatic"),
        ("InteractiveSearch", "manual"),
        ("Unknown", "unknown"),
        ("FutureSource", "unknown"),
        ("", "unknown"),
        (None, "unknown"),
        ("  iNteRactIveSearch  ", "manual"),
        (" rSS ", "automatic"),
    ],
)
def test_origin_classification(client: Radarr | Sonarr, source: str | None, origin: str) -> None:
    handler = _handler(client)
    handler.request.return_value = {
        "records": [_record(data={"ReLeAsEsOuRcE": source})],
        "totalRecords": 1,
    }

    assert client.get_download_origin("download-7") == origin
    handler.request.assert_called_once_with(
        "history",
        params={"downloadId": "download-7", "eventType": 1, "page": 1, "pageSize": 100},
    )


@pytest.mark.parametrize(
    "records",
    [
        [],
        [_record(data={})],
        [_record(downloadId="different-download")],
        [_record(downloadId=None)],
        [_record(eventType="downloadFolderImported")],
        [_record(eventType=3)],
        [_record(), _record(data={"releaseSource": "Unknown"})],
        [_record(data={"releaseSource": "Rss", "ReleaseSource": "Unknown"})],
    ],
)
def test_unreliable_history_is_unknown(
    client: Radarr | Sonarr, records: list[dict[str, object]]
) -> None:
    _handler(client).request.return_value = {"records": records, "totalRecords": len(records)}

    assert client.get_download_origin("download-7") == "unknown"


@pytest.mark.parametrize("event_type", ["grabbed", "GRABBED", 1])
def test_duplicate_episode_grabs_are_automatic(
    client: Radarr | Sonarr, event_type: str | int
) -> None:
    _handler(client).request.return_value = {
        "records": [_record(eventType=event_type), _record(eventType=event_type)],
        "totalRecords": 2,
    }

    assert client.get_download_origin("download-7") == "automatic"


def test_paginates_and_preserves_manual_origin_on_later_page(client: Radarr | Sonarr) -> None:
    handler = _handler(client)
    handler.request.side_effect = [
        {"records": [_record()] * 100, "totalRecords": 101},
        {"records": [_record(data={"releaseSource": "InteractiveSearch"})], "totalRecords": 101},
    ]

    assert client.get_download_origin("download-7") == "manual"
    assert handler.request.call_count == 2
    handler.request.assert_any_call(
        "history",
        params={"downloadId": "download-7", "eventType": 1, "page": 2, "pageSize": 100},
    )


def test_paginates_without_total_records(client: Radarr | Sonarr) -> None:
    handler = _handler(client)
    handler.request.side_effect = [{"records": [_record()] * 100}, {"records": []}]

    assert client.get_download_origin("download-7") == "automatic"
    assert handler.request.call_count == 2


def test_incomplete_history_cannot_authorize_cleanup(client: Radarr | Sonarr) -> None:
    handler = _handler(client)
    handler.request.side_effect = [
        {"records": [_record()], "totalRecords": 2},
        {"records": [], "totalRecords": 2},
    ]

    assert client.get_download_origin("download-7") == "unknown"


@pytest.mark.parametrize("download_id", ["", " ", "\t"])
def test_blank_id_does_not_fetch_history(client: Radarr | Sonarr, download_id: str) -> None:
    assert client.get_download_origin(download_id) == "unknown"
    _handler(client).request.assert_not_called()


@pytest.mark.parametrize(
    "response",
    [None, [], {}, {"records": "invalid"}, {"records": [_record(data=None)]}],
)
def test_malformed_history_raises(client: Radarr | Sonarr, response: object) -> None:
    _handler(client).request.return_value = response

    with pytest.raises(ValidationError):
        client.get_download_origin("download-7")


def test_history_failure_propagates(client: Radarr | Sonarr) -> None:
    _handler(client).request.side_effect = RuntimeError("unavailable")

    with pytest.raises(RuntimeError, match="unavailable"):
        client.get_download_origin("download-7")


@pytest.mark.parametrize("download_id", [None, "", " ", "download-7"])
def test_queue_item_download_id_alias(download_id: str | None) -> None:
    item = ArrQueueItem.model_validate(
        {
            "id": 7,
            "title": "Movie",
            "protocol": "torrent",
            "status": "completed",
            "downloadId": download_id,
        }
    )

    assert item.download_id == download_id


def test_queue_item_download_id_defaults_to_none() -> None:
    item = ArrQueueItem.model_validate(
        {"id": 7, "title": "Movie", "protocol": "usenet", "status": "completed"}
    )

    assert item.download_id is None
