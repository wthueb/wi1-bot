"""End-to-end tests for Autobrr release pushes through the webhook Arr facade."""

from collections.abc import Generator
from typing import Any

import pytest
import requests

# Must match the committed Arr seeds and the webhook e2e configuration.
_ARR_HEADERS = {"X-Api-Key": "0123456789abcdef0123456789abcdef"}


def _configure_usenet_blackhole(arr_url: str, folder: str) -> None:
    schema_response = requests.get(
        f"{arr_url}/api/v3/downloadclient/schema",
        headers=_ARR_HEADERS,
        timeout=30,
    )
    schema_response.raise_for_status()
    schemas: Any = schema_response.json()
    blackhole = next(
        schema for schema in schemas if schema.get("implementation") == "UsenetBlackhole"
    )
    blackhole["name"] = "e2e-usenet-blackhole"
    blackhole["enable"] = True
    for field in blackhole["fields"]:
        if field.get("name") == "nzbFolder":
            field["value"] = f"{folder}/nzb"
        elif field.get("name") == "watchFolder":
            field["value"] = f"{folder}/watch"

    create_response = requests.post(
        f"{arr_url}/api/v3/downloadclient",
        headers=_ARR_HEADERS,
        json=blackhole,
        timeout=30,
    )
    create_response.raise_for_status()


@pytest.fixture(scope="session")
def autobrr_download_clients(services: dict[str, str]) -> Generator[None, None, None]:
    for kind in ("radarr", "sonarr"):
        _configure_usenet_blackhole(services[f"{kind}_url"], f"/media/blackhole/{kind}")
    yield


def _push(services: dict[str, str], kind: str, title: str) -> requests.Response:
    return requests.post(
        f"{services['webhook_url']}/autobrr/{kind}/api/v3/release/push",
        json={
            "title": title,
            "infoUrl": "https://indexer.invalid/details/1",
            "downloadUrl": "http://e2e-release-server:8080/release.nzb",
            "size": 1_000_000_000,
            "indexer": "e2e-indexer",
            "downloadProtocol": "usenet",
            "protocol": "usenet",
            "publishDate": "2026-08-11T12:00:00Z",
        },
        timeout=30,
    )


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("kind", "title"),
    [
        ("radarr", "Big.Buck.Bunny.2008.1080p.BluRay-GROUP"),
        ("sonarr", "Over.the.Garden.Wall.S01E01.1080p.BluRay-GROUP"),
    ],
)
def test_autobrr_release_push_is_approved_by_real_arr(
    services: dict[str, str],
    autobrr_download_clients: None,
    kind: str,
    title: str,
) -> None:
    response = _push(services, kind, title)

    assert response.status_code == 200
    assert response.json() == [
        {
            "approved": True,
            "rejected": False,
            "temporarilyRejected": False,
            "rejections": [],
        }
    ]


@pytest.mark.e2e
@pytest.mark.parametrize(
    ("kind", "title"),
    [
        ("radarr", "Definitely.Not.In.Library.2026.1080p.WEB-DL-GROUP"),
        ("sonarr", "Definitely.Not.In.Library.S01E01.1080p.WEB-DL-GROUP"),
    ],
)
def test_autobrr_release_push_returns_real_arr_rejection(
    services: dict[str, str], kind: str, title: str
) -> None:
    response = _push(services, kind, title)

    assert response.status_code == 200
    body: Any = response.json()
    assert isinstance(body, list) and len(body) == 1
    result = body[0]
    assert result["approved"] is False
    assert result["rejected"] is True
    assert result["temporarilyRejected"] is False
    assert len(result["rejections"]) == 1
    assert result["rejections"][0].startswith(f"{kind}: ")
