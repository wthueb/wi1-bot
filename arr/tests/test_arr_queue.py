from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pyarr import PyarrResourceNotFound
from pydantic import ValidationError

from wi1_bot.arr.queue import ArrQueueItem, ArrQueueItemNotFound
from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr


@pytest.fixture
def radarr() -> Radarr:
    with patch("wi1_bot.arr.radarr.RadarrClient"):
        return Radarr("http://localhost:7878", "fake-api-key")


@pytest.fixture
def sonarr() -> Sonarr:
    with patch("wi1_bot.arr.sonarr.SonarrClient"):
        return Sonarr("http://localhost:8989", "fake-api-key")


def _queue_api(client: Radarr | Sonarr) -> MagicMock:
    queue = client._radarr.queue if isinstance(client, Radarr) else client._sonarr.queue
    return cast(MagicMock, queue)


def _item(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "id": 7,
        "title": "Movie.2026.E2ELOW",
        "protocol": "usenet",
        "status": "completed",
        "trackedDownloadStatus": "warning",
        "trackedDownloadState": "importBlocked",
        "statusMessages": [
            {
                "title": "Movie.mkv",
                "messages": [
                    "Not a Custom Format upgrade for existing movie file(s). New: [] (10)"
                ],
            }
        ],
        "ignoredUpstreamField": True,
    }
    data.update(overrides)
    return data


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_get_queue_items_validates_and_paginates(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    queue_api = _queue_api(client)
    queue_api.get.side_effect = [
        {"records": [_item(id=1), _item(id=2)], "totalRecords": 3},
        {"records": [_item(id=3)], "totalRecords": 3},
    ]

    items = client.get_queue_items(page_size=2)

    assert [item.id for item in items] == [1, 2, 3]
    assert all(item.is_custom_format_downgrade for item in items)
    assert queue_api.get.call_count == 2
    queue_api.get.assert_any_call(page=1, page_size=2)
    queue_api.get.assert_any_call(page=2, page_size=2)


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_get_queue_items_rejects_malformed_records(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    _queue_api(client).get.return_value = {"records": [_item(protocol="ftp")]}

    with pytest.raises(ValidationError):
        client.get_queue_items()


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": "downloading"},
        {"trackedDownloadStatus": "ok"},
        {"trackedDownloadState": "importing"},
        {
            "statusMessages": [
                {"title": "Movie.mkv", "messages": ["Not an upgrade for existing movie file"]}
            ]
        },
        {
            "statusMessages": [
                {
                    "title": "Movie.mkv",
                    "messages": ["Not a quality revision upgrade for existing movie file(s)"],
                }
            ]
        },
    ],
)
def test_custom_format_downgrade_matcher_rejects_near_misses(
    overrides: dict[str, object],
) -> None:
    assert not ArrQueueItem.model_validate(_item(**overrides)).is_custom_format_downgrade


@pytest.mark.parametrize("tracked_download_state", ["importBlocked", "importPending"])
def test_custom_format_downgrade_matches_blocked_and_pending_states(
    tracked_download_state: str,
) -> None:
    item = ArrQueueItem.model_validate(_item(trackedDownloadState=tracked_download_state))

    assert item.is_custom_format_downgrade


def test_custom_format_after_rename_message_matches() -> None:
    item = ArrQueueItem.model_validate(
        _item(
            statusMessages=[
                {
                    "title": "Episode.mkv",
                    "messages": [
                        "Not a Custom Format upgrade for existing episode file(s). "
                        "AfterRename: [] (0) do not improve on Existing: [High] (100)"
                    ],
                }
            ]
        )
    )

    assert item.is_custom_format_downgrade


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
@pytest.mark.parametrize("remove_from_client", [False, True])
def test_remove_queue_item_uses_safe_arr_options(
    client_fixture: str,
    remove_from_client: bool,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    queue_api = _queue_api(client)

    client.remove_queue_item(7, remove_from_client=remove_from_client)

    queue_api.delete.assert_called_once_with(
        7,
        remove_from_client=remove_from_client,
        blocklist=False,
    )


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_remove_queue_item_normalizes_not_found(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    _queue_api(client).delete.side_effect = PyarrResourceNotFound("gone")

    with pytest.raises(ArrQueueItemNotFound):
        client.remove_queue_item(7, remove_from_client=True)
