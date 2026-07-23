#!/usr/bin/env python3
"""Regenerate the committed Radarr seed used by the e2e pipeline test.

Boots a fresh, pinned Radarr with a fixed API key, configures it via the v3 API (root
folder, quality profile, the seeded movie, and the On Import webhook Connect), then
snapshots ``config.xml`` + ``radarr.db`` into ``radarr/``.

Run this only when bumping the pinned Radarr image (RADARR_IMAGE) or changing the seed. It
needs Docker and internet access (Radarr looks the movie up via TMDB once, here — never at
test time). Usage:

    python tests/e2e/seed/regenerate_radarr.py

See README.md in this directory for details.
"""

import shutil
import sys
import tempfile
from pathlib import Path

from _seed_common import (
    WEBHOOK_URL,
    ArrApi,
    config_xml,
    run_docker,
    snapshot,
    start_arr,
    start_seed_network,
    teardown_seed_network,
)

# keep RADARR_IMAGE in sync with the wi1-bot-radarr image in tests/e2e/compose.yaml
RADARR_IMAGE = "lscr.io/linuxserver/radarr:6.3.0.10514-ls311"
CONTAINER = "wi1bot-e2e-radarr-seed"
HOST_PORT = 17878
ROOT_FOLDER = "/media/movies"
# "Any" (a default profile) accepts the blacked-out clip's quality; must match the
# transcoder profile name
QUALITY_PROFILE = "Any"
MOVIE_TMDB_ID = 10378  # Big Buck Bunny (2008)
SEED_DIR = Path(__file__).parent / "radarr"


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="wi1bot-seed-"))
    config_dir = work / "config"
    media_dir = work / "media"
    (media_dir / "movies").mkdir(parents=True)
    config_dir.mkdir()
    (config_dir / "config.xml").write_text(config_xml("Radarr", 7878))

    teardown_seed_network(CONTAINER)  # clean up any leftovers from a previous run
    start_seed_network()
    start_arr(CONTAINER, RADARR_IMAGE, HOST_PORT, 7878, config_dir, media_dir)

    try:
        api = ArrApi(f"http://localhost:{HOST_PORT}")
        print("waiting for the Radarr API ...")
        api.wait_ready()

        print(f"adding root folder {ROOT_FOLDER} ...")
        api.request("POST", "/api/v3/rootfolder", json={"path": ROOT_FOLDER})

        profile_id = api.quality_profile_id(QUALITY_PROFILE)

        print(f"adding movie tmdb:{MOVIE_TMDB_ID} with profile {QUALITY_PROFILE} ...")
        lookup = api.request(
            "GET", "/api/v3/movie/lookup", params={"term": f"tmdb:{MOVIE_TMDB_ID}"}
        ).json()
        movie = lookup[0] if isinstance(lookup, list) else lookup
        movie.update(
            {
                "qualityProfileId": profile_id,
                "rootFolderPath": ROOT_FOLDER,
                "monitored": True,
                "minimumAvailability": "released",
                "addOptions": {"searchForMovie": False},
            }
        )
        api.request("POST", "/api/v3/movie", json=movie)

        print(f"adding On Import webhook -> {WEBHOOK_URL} ...")
        api.add_webhook_notification()

        print("stopping the container to flush the database ...")
        run_docker("stop", CONTAINER)
    finally:
        run_docker("stop", CONTAINER, check=False)  # snapshot needs the DB flushed first

    snapshot(config_dir, SEED_DIR, "radarr.db")
    teardown_seed_network(CONTAINER)
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote seed to {SEED_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
