"""End-to-end tests for Autobrr release pushes through the webhook Arr facade."""

from typing import Any

import pytest
import requests


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
    usenet_blackhole_clients: None,
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
