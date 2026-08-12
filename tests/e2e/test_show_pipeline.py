"""End-to-end test of the TV-episode transcoding pipeline.

The Sonarr counterpart to test_movie_pipeline.py: a completed episode "download" is
pushed to a seeded Sonarr, which imports it and fires its On Import webhook; the webhook
enqueues a job; the transcoder worker claims it, runs ffmpeg, and reports back; the webhook
triggers a rescan and Sonarr re-imports the transcoded file. Success = the series has an
episode file that is the transcoded one.
"""

import time
from typing import Any

import pytest

from wi1_bot.arr.sonarr import Sonarr

TIMEOUT = 240.0
POLL = 3.0


def _episode_file_relpath(
    sonarr: Sonarr,
    series_id: int,
    season_number: int,
    episode_number: int,
) -> str | None:
    """Return one episode's current file path without relying on other series files."""
    episodes: Any = sonarr._sonarr.episode.get(series_id=series_id)
    episode = next(
        ep
        for ep in episodes
        if ep.get("seasonNumber") == season_number and ep.get("episodeNumber") == episode_number
    )
    file_id = int(episode.get("episodeFileId", 0))
    if file_id == 0:
        return None

    episode_file: Any = sonarr._sonarr.episode_file.get(item_id=file_id)
    return str(episode_file.get("relativePath", ""))


@pytest.mark.e2e
def test_episode_transcode_pipeline(sonarr: Sonarr, series_id: int, series_scan_path: str) -> None:
    # S01E01 starts with no file; other e2e tests may independently use S01E02
    assert _episode_file_relpath(sonarr, series_id, 1, 1) is None

    # simulate a completed download: Sonarr copies the blacked-out file into the library
    # (from the read-only /fixtures mount) and fires its On Import webhook
    sonarr._sonarr.command.execute(
        name="DownloadedEpisodesScan", path=series_scan_path, importMode=2
    )

    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        relpath = _episode_file_relpath(sonarr, series_id, 1, 1)
        if relpath is not None and "TRANSCODED" in relpath:
            return
        time.sleep(POLL)

    pytest.fail(
        f"no transcoded episode file appeared within {TIMEOUT:.0f}s. Inspect with "
        f"`docker compose -f tests/e2e/compose.yaml logs`."
    )
