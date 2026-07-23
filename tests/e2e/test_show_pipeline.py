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


def _has_transcoded_file(sonarr: Sonarr, series_id: int) -> bool:
    """Whether any of the series' episode files is a transcoded one."""
    # pyarr returns loosely-typed JSON here, hence Any
    files: Any = sonarr._sonarr.episode_file.get(series_id=series_id)
    return any("TRANSCODED" in f.get("relativePath", "") for f in files)


@pytest.mark.e2e
def test_episode_transcode_pipeline(sonarr: Sonarr, series_id: int, series_scan_path: str) -> None:
    # the seeded series starts with no episode files
    assert sonarr.get_series_by_id(series_id)["statistics"]["episodeFileCount"] == 0

    # simulate a completed download: Sonarr copies the blacked-out file into the library
    # (from the read-only /fixtures mount) and fires its On Import webhook
    sonarr._sonarr.command.execute(
        name="DownloadedEpisodesScan", path=series_scan_path, importMode=2
    )

    deadline = time.monotonic() + TIMEOUT
    while time.monotonic() < deadline:
        if _has_transcoded_file(sonarr, series_id):
            return
        time.sleep(POLL)

    pytest.fail(
        f"no transcoded episode file appeared within {TIMEOUT:.0f}s. Inspect with "
        f"`docker compose -f tests/e2e/compose.yaml logs`."
    )
