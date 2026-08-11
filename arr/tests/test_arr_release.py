import json
from typing import cast
from unittest.mock import MagicMock, patch

import pytest
from pyarr import PyarrBadRequest
from pydantic import ValidationError

from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.release import (
    ReleasePushConfigurationError,
    ReleasePushRequest,
    ReleasePushResult,
)
from wi1_bot.arr.sonarr import Sonarr


@pytest.fixture
def radarr() -> Radarr:
    with patch("wi1_bot.arr.radarr.RadarrClient"):
        return Radarr("http://localhost:7878", "fake-api-key")


@pytest.fixture
def sonarr() -> Sonarr:
    with patch("wi1_bot.arr.sonarr.SonarrClient"):
        return Sonarr("http://localhost:8989", "fake-api-key")


def _request() -> ReleasePushRequest:
    return ReleasePushRequest.model_validate(
        {
            "title": "Show.S01E01.1080p-GROUP",
            "infoUrl": "https://indexer.example/details/1",
            "downloadUrl": "https://indexer.example/download?id=1",
            "magnetUrl": "magnet:?xt=urn:btih:abc",
            "size": 1234,
            "indexer": "tracker",
            "downloadProtocol": "torrent",
            "protocol": "torrent",
            "publishDate": "2026-08-11T12:00:00Z",
            "downloadClientId": 3,
            "downloadClient": "qbit",
            "indexerFlags": 5,
            "futureField": "preserved",
        }
    )


def _release_handler(client: Radarr | Sonarr) -> MagicMock:
    release_api = client._radarr.release if isinstance(client, Radarr) else client._sonarr.release
    return cast(MagicMock, release_api.handler)


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_push_release_forwards_native_payload_and_validates_response(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    handler = _release_handler(client)
    handler.request.return_value = [
        {
            "approved": True,
            "rejected": False,
            "temporarilyRejected": False,
            "rejections": [],
            "ignoredUpstreamField": "value",
        }
    ]
    push_request = _request()

    result = client.push_release(push_request)

    assert result == [
        ReleasePushResult(
            approved=True,
            rejected=False,
            temporarilyRejected=False,
        )
    ]
    handler.request.assert_called_once_with(
        "release/push",
        method="POST",
        json_data={
            "title": "Show.S01E01.1080p-GROUP",
            "infoUrl": "https://indexer.example/details/1",
            "downloadUrl": "https://indexer.example/download?id=1",
            "magnetUrl": "magnet:?xt=urn:btih:abc",
            "size": 1234,
            "indexer": "tracker",
            "downloadProtocol": "torrent",
            "protocol": "torrent",
            "publishDate": "2026-08-11T12:00:00Z",
            "downloadClientId": 3,
            "downloadClient": "qbit",
            "indexerFlags": 5,
            "futureField": "preserved",
        },
    )


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_push_release_omits_zero_download_client_id(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    handler = _release_handler(client)
    handler.request.return_value = [
        {
            "approved": True,
            "rejected": False,
            "temporarilyRejected": False,
        }
    ]
    push_request = _request().model_copy(update={"download_client_id": 0})

    client.push_release(push_request)

    payload = handler.request.call_args.kwargs["json_data"]
    assert "downloadClientId" not in payload


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
@pytest.mark.parametrize(
    "response",
    [
        [],
        [{"approved": "not-a-boolean"}],
        [
            {
                "approved": False,
                "rejected": False,
                "temporarilyRejected": False,
            }
        ],
    ],
)
def test_push_release_rejects_malformed_response(
    client_fixture: str,
    response: object,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    _release_handler(client).request.return_value = response

    with pytest.raises((ValidationError, ValueError)):
        client.push_release(_request())


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_push_release_turns_bad_request_into_rejection(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    _release_handler(client).request.side_effect = PyarrBadRequest(
        json.dumps(
            [
                {
                    "propertyName": "Title",
                    "errorMessage": "Unable to parse",
                    "errorCode": "",
                    "attemptedValue": "bad title",
                    "severity": "error",
                }
            ]
        )
    )

    assert client.push_release(_request()) == [
        ReleasePushResult(
            approved=False,
            rejected=True,
            temporarilyRejected=False,
            rejections=["[error: ] Title: Unable to parse - got value: bad title"],
        )
    ]


@pytest.mark.parametrize("client_fixture", ["radarr", "sonarr"])
def test_push_release_treats_bad_download_client_as_configuration_error(
    client_fixture: str,
    request: pytest.FixtureRequest,
) -> None:
    client: Radarr | Sonarr = request.getfixturevalue(client_fixture)
    _release_handler(client).request.side_effect = PyarrBadRequest(
        json.dumps(
            [
                {
                    "propertyName": "DownloadClientId",
                    "errorMessage": "Download client does not exist",
                    "errorCode": "InvalidValue",
                    "attemptedValue": 3,
                    "severity": "error",
                }
            ]
        )
    )

    with pytest.raises(ReleasePushConfigurationError, match="invalid download client"):
        client.push_release(_request())


def test_release_push_request_requires_download_location() -> None:
    with pytest.raises(ValidationError):
        ReleasePushRequest.model_validate(
            {
                "title": "Movie.2026.1080p-GROUP",
                "downloadProtocol": "torrent",
                "protocol": "torrent",
                "publishDate": "2026-08-11T12:00:00Z",
            }
        )


def test_release_push_result_api_shape() -> None:
    result = ReleasePushResult(
        approved=False,
        rejected=True,
        temporarilyRejected=True,
        rejections=["Quality for existing file on disk is of equal or higher preference"],
    )

    assert result.as_api_dict() == {
        "approved": False,
        "rejected": True,
        "temporarilyRejected": True,
        "rejections": ["Quality for existing file on disk is of equal or higher preference"],
    }
