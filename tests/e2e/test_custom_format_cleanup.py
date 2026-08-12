"""End-to-end coverage for automatic custom-format downgrade cleanup.

This reproduces the ordering from issue #42 against real Sonarr and webhook containers:
the lower-scored release is grabbed, the higher-scored release imports, then the lower
release completes and becomes import-blocked. The webhook must remove the usenet item and
its content without replacing the higher-scored episode file.
"""

import subprocess
import time
from typing import Any

import pytest
import requests

from wi1_bot.arr.sonarr import Sonarr

TIMEOUT = 180.0
IMPORT_TIMEOUT = 60.0
POLL = 2.0
API_KEY = "0123456789abcdef0123456789abcdef"
SONARR_SERVICE = "wi1-bot-sonarr"
HIGH_FORMAT = "E2E High"
LOW_FORMAT = "E2E Low"
LOW_RELEASE = "Over.the.Garden.Wall.S01E02.1080p.BluRay.E2ELOW-GROUP"
LOW_WATCH_PATH = f"/media/blackhole/sonarr/watch/{LOW_RELEASE}"
_ARR_HEADERS = {"X-Api-Key": API_KEY}


def _arr_request(
    services: dict[str, str],
    method: str,
    path: str,
    json: object | None = None,
) -> Any:
    response = requests.request(
        method,
        f"{services['sonarr_url']}/api/v3{path}",
        headers=_ARR_HEADERS,
        timeout=30,
        json=json,
    )
    response.raise_for_status()
    return response.json() if response.content else None


def _create_release_title_format(services: dict[str, str], name: str, marker: str) -> int:
    result = _arr_request(
        services,
        "POST",
        "/customformat",
        json={
            "name": name,
            "includeCustomFormatWhenRenaming": True,
            "specifications": [
                {
                    "name": marker,
                    "implementation": "ReleaseTitleSpecification",
                    "negate": False,
                    "required": True,
                    "fields": [{"name": "value", "value": rf"\b{marker}\b"}],
                }
            ],
        },
    )
    return int(result["id"])


def _configure_profile(services: dict[str, str]) -> tuple[dict[str, Any], int]:
    profiles: Any = _arr_request(services, "GET", "/qualityprofile")
    profile = next(profile for profile in profiles if profile["name"] == "Any")
    high_id = _create_release_title_format(services, HIGH_FORMAT, "E2EHIGH")
    low_id = _create_release_title_format(services, LOW_FORMAT, "E2ELOW")
    profile["name"] = "E2E Cleanup"
    profile["formatItems"] = [
        {"format": high_id, "name": HIGH_FORMAT, "score": 100},
        {"format": low_id, "name": LOW_FORMAT, "score": 10},
    ]
    _arr_request(
        services,
        "PUT",
        f"/qualityprofile/{profile['id']}",
        json=profile,
    )
    return profile.copy(), int(profile["id"])


def _episode(sonarr: Sonarr, series_id: int, episode_number: int) -> dict[str, Any]:
    episodes: Any = sonarr._sonarr.episode.get(series_id=series_id)
    return next(
        episode
        for episode in episodes
        if episode.get("seasonNumber") == 1 and episode.get("episodeNumber") == episode_number
    )


def _episode_file(sonarr: Sonarr, series_id: int, episode_number: int) -> dict[str, Any] | None:
    episode = _episode(sonarr, series_id, episode_number)
    file_id = int(episode.get("episodeFileId", 0))
    if file_id == 0:
        return None
    result: Any = sonarr._sonarr.episode_file.get(item_id=file_id)
    return result


def _push_low_release(services: dict[str, str]) -> None:
    response = requests.post(
        f"{services['webhook_url']}/autobrr/sonarr/api/v3/release/push",
        json={
            "title": LOW_RELEASE,
            "infoUrl": "https://indexer.invalid/details/custom-format-low",
            "downloadUrl": "http://e2e-release-server:8080/release.nzb",
            "size": 1_000_000_000,
            "indexer": "e2e-indexer",
            "downloadProtocol": "usenet",
            "protocol": "usenet",
            "publishDate": "2026-08-12T12:00:00Z",
        },
        timeout=30,
    )
    response.raise_for_status()
    assert response.json()[0]["approved"] is True


def _compose_exec(
    compose_file: str,
    project_name: str,
    *command: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            compose_file,
            "-p",
            project_name,
            "exec",
            "-T",
            SONARR_SERVICE,
            *command,
        ],
        check=check,
        capture_output=True,
        text=True,
    )


def _cleanup_removed_count(webhook_url: str) -> float:
    response = requests.get(f"{webhook_url}/metrics", timeout=30)
    response.raise_for_status()
    metric = "wi1_bot_webhook_queue_cleanup_items_total"
    labels = ('outcome="removed"', 'protocol="usenet"', 'target="sonarr"')
    for line in response.text.splitlines():
        if line.startswith(f"{metric}{{") and all(label in line for label in labels):
            return float(line.rsplit(" ", 1)[1])
    return 0.0


@pytest.mark.e2e
def test_usenet_custom_format_downgrade_is_removed(
    services: dict[str, str],
    sonarr: Sonarr,
    series_id: int,
    custom_format_paths: dict[str, str],
    usenet_blackhole_clients: None,
    docker_compose_file: str,
    docker_compose_project_name: str,
) -> None:
    assert _episode_file(sonarr, series_id, 2) is None
    original_profile, profile_id = _configure_profile(services)
    removed_before = _cleanup_removed_count(services["webhook_url"])

    try:
        # B is grabbed before A is imported, matching the race described in the issue.
        _push_low_release(services)
        sonarr._sonarr.command.execute(
            name="DownloadedEpisodesScan",
            path=custom_format_paths["high_scan"],
            importMode=2,
        )

        deadline = time.monotonic() + IMPORT_TIMEOUT
        high_file: dict[str, Any] | None = None
        while time.monotonic() < deadline:
            high_file = _episode_file(sonarr, series_id, 2)
            if high_file is not None and any(
                custom_format.get("name") == HIGH_FORMAT
                for custom_format in high_file.get("customFormats", [])
            ):
                break
            time.sleep(POLL)
        else:
            pytest.fail("the high-scored S01E02 file was not imported by Sonarr")

        assert high_file is not None
        high_file_id = int(high_file["id"])

        # Completing the already-grabbed B release now produces the import-blocked
        # custom-format downgrade that the webhook worker polls for.
        _compose_exec(
            docker_compose_file,
            docker_compose_project_name,
            "mkdir",
            "-p",
            LOW_WATCH_PATH,
        )
        _compose_exec(
            docker_compose_file,
            docker_compose_project_name,
            "cp",
            custom_format_paths["low_source"],
            f"{LOW_WATCH_PATH}/{LOW_RELEASE}.mkv",
        )

        deadline = time.monotonic() + TIMEOUT
        while time.monotonic() < deadline:
            if _cleanup_removed_count(services["webhook_url"]) > removed_before:
                break
            time.sleep(POLL)
        else:
            pytest.fail("the webhook did not remove the usenet custom-format downgrade")

        assert all(item.title != LOW_RELEASE for item in sonarr.get_queue_items())
        _compose_exec(
            docker_compose_file,
            docker_compose_project_name,
            "test",
            "!",
            "-e",
            LOW_WATCH_PATH,
        )
        current_file = _episode_file(sonarr, series_id, 2)
        assert current_file is not None
        assert int(current_file["id"]) == high_file_id
    finally:
        original_profile["name"] = "Any"
        _arr_request(
            services,
            "PUT",
            f"/qualityprofile/{profile_id}",
            json=original_profile,
        )
