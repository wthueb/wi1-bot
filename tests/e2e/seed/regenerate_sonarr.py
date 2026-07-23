#!/usr/bin/env python3
"""Regenerate the committed Sonarr seed used by the e2e pipeline test.

Boots a fresh, pinned Sonarr with a fixed API key, configures it via the v3 API (root
folder, quality profile, the seeded series, and the On Import webhook Connect), then
snapshots ``config.xml`` + ``sonarr.db`` into ``sonarr/``.

Run this only when bumping the pinned Sonarr image (SONARR_IMAGE) or changing the seed. It
needs Docker and internet access (Sonarr looks the series up via TheTVDB once, here — never
at test time). Usage:

    python tests/e2e/seed/regenerate_sonarr.py

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

# keep SONARR_IMAGE in sync with the wi1-bot-sonarr image in tests/e2e/compose.yaml, and
# SERIES_TITLE in sync with conftest.py's SERIES_TITLE
SONARR_IMAGE = "lscr.io/linuxserver/sonarr:4.0.19.2979-ls320"
CONTAINER = "wi1bot-e2e-sonarr-seed"
HOST_PORT = 18989
ROOT_FOLDER = "/media/tv"
# "Any" (a default profile) accepts the blacked-out clip's quality; must match the
# transcoder profile name
QUALITY_PROFILE = "Any"
# a short-episode (~11 min) 10-episode miniseries, so the looped clip clears Sonarr's
# sample-detection threshold (Chernobyl's ~65 min episodes did not)
SERIES_TITLE = "Over the Garden Wall"
SEED_DIR = Path(__file__).parent / "sonarr"


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="wi1bot-seed-"))
    config_dir = work / "config"
    media_dir = work / "media"
    (media_dir / "tv").mkdir(parents=True)
    config_dir.mkdir()
    (config_dir / "config.xml").write_text(config_xml("Sonarr", 8989))

    teardown_seed_network(CONTAINER)  # clean up any leftovers from a previous run
    start_seed_network()
    start_arr(CONTAINER, SONARR_IMAGE, HOST_PORT, 8989, config_dir, media_dir)

    try:
        api = ArrApi(f"http://localhost:{HOST_PORT}")
        print("waiting for the Sonarr API ...")
        api.wait_ready()

        print(f"adding root folder {ROOT_FOLDER} ...")
        api.request("POST", "/api/v3/rootfolder", json={"path": ROOT_FOLDER})

        profile_id = api.quality_profile_id(QUALITY_PROFILE)

        print(f"adding series {SERIES_TITLE!r} with profile {QUALITY_PROFILE} ...")
        lookup = api.request("GET", "/api/v3/series/lookup", params={"term": SERIES_TITLE}).json()
        series = next((s for s in lookup if s.get("title") == SERIES_TITLE), None)
        if series is None:
            raise RuntimeError(f"no series titled {SERIES_TITLE!r} found")
        series.update(
            {
                "qualityProfileId": profile_id,
                "rootFolderPath": ROOT_FOLDER,
                "monitored": True,
                "seasonFolder": True,
                "addOptions": {
                    "monitor": "all",
                    "searchForMissingEpisodes": False,
                    "searchForCutoffUnmetEpisodes": False,
                },
            }
        )
        api.request("POST", "/api/v3/series", json=series)

        print(f"adding On Import webhook -> {WEBHOOK_URL} ...")
        api.add_webhook_notification()

        print("stopping the container to flush the database ...")
        run_docker("stop", CONTAINER)
    finally:
        run_docker("stop", CONTAINER, check=False)  # snapshot needs the DB flushed first

    snapshot(config_dir, SEED_DIR, "sonarr.db")
    teardown_seed_network(CONTAINER)
    shutil.rmtree(work, ignore_errors=True)
    print(f"wrote seed to {SEED_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
