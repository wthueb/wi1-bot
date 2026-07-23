"""End-to-end test of the movie transcoding pipeline.

Drives the real loop through real containers: a completed "download" is pushed to a
seeded Radarr, which imports it and fires its On Import webhook; the webhook enqueues a
job; the transcoder worker claims it, runs ffmpeg, and reports back; the webhook triggers
a rescan and Radarr re-imports the transcoded file. Success = the movie's current file
is the transcoded one.
"""

import time
from typing import Any

import pytest

from wi1_bot.arr.radarr import Radarr

TIMEOUT = 240.0
POLL = 3.0


def _current_relpath(radarr: Radarr, movie_id: int) -> str | None:
    """The movie's current file's relative path, or None if it has no file yet."""
    movie = radarr.get_movie_by_id(movie_id)
    movie_file = movie.get("movieFile")
    if movie_file and movie_file.get("relativePath"):
        return str(movie_file["relativePath"])
    # /movie/{id} may omit movieFile in some versions; fall back to the file endpoint
    # (pyarr returns loosely-typed JSON here, hence Any)
    if movie.get("movieFileId", 0):
        files: Any = radarr._radarr.movie_file.get(movie_id=movie_id)
        if files:
            return str(files[0].get("relativePath", ""))
    return None


@pytest.mark.e2e
def test_movie_transcode_pipeline(radarr: Radarr, movie_id: int, movie_scan_path: str) -> None:
    # the seeded movie starts with no file imported
    assert radarr.get_movie_by_id(movie_id).get("movieFileId", 0) == 0

    # simulate a completed download: Radarr copies the blacked-out file into the library
    # (from the read-only /fixtures mount) and fires its On Import webhook
    radarr._radarr.command.execute(name="DownloadedMoviesScan", path=movie_scan_path, importMode=2)

    deadline = time.monotonic() + TIMEOUT
    last_seen = "<no file imported>"
    while time.monotonic() < deadline:
        rel = _current_relpath(radarr, movie_id)
        if rel:
            last_seen = rel
            # the transcoder writes "<stem>-TRANSCODED.mkv"; once Radarr re-imports it,
            # the movie's current file is the transcoded one -> the full loop ran
            if "TRANSCODED" in rel:
                return
        time.sleep(POLL)

    pytest.fail(
        f"transcoded file never became the movie's file within {TIMEOUT:.0f}s "
        f"(last imported file: {last_seen!r}). Inspect with "
        f"`docker compose -f tests/e2e/compose.yaml logs`."
    )
