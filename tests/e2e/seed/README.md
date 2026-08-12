# *arr e2e seeds

`radarr/` and `sonarr/` each hold a pre-configured `/config` (`config.xml` + the app DB)
used by the end-to-end pipeline tests (`tests/e2e/test_movie_pipeline.py` and
`test_show_pipeline.py`). Mounting them into fresh Radarr/Sonarr containers gives
deterministic, offline-capable instances — no download client, indexer, or TMDB/TheTVDB
lookup is needed at test time.

Each seed contains:

- a **fixed API key** (`0123456789abcdef0123456789abcdef`) so the webhook config and the
  tests can authenticate without discovering a random key — a throwaway test credential,
  not a secret;
- an **instance name** (`Radarr` / `Sonarr`) matching `tests/e2e/config/webhook.yaml` and
  the `instanceName` the *arr sends in its webhook payload;
- a **root folder** (`/media/movies` / `/media/tv`);
- one **monitored library item**, assigned the default **`Any`** quality profile (which
  must match the transcoder profile name in `tests/e2e/config/transcoder.yaml`; `Any`
  avoids resolution/quality mismatches on import), with no file yet:
  - Radarr: *Big Buck Bunny (2008)* (tmdb 10378), a public-domain film;
  - Sonarr: *Over the Garden Wall* (2014), a 10-episode miniseries whose ~11-min episodes
    are short enough that the looped test clip clears Sonarr's sample detection;
- an **On Import webhook Connect** pointing at `http://wi1-bot-webhook:9000/`.

The e2e fixture setup also derives S01E02 high/low custom-format download files from the
committed blacked-out clip. The cleanup test configures its custom formats and usenet
blackhole client through the live Sonarr API, so those test-specific settings do not need
to be persisted in the seed database.

## Regenerating

Run these only when bumping a pinned *arr image or changing a seed's contents. They need
Docker and internet access (the library item is looked up via TMDB/TheTVDB once, here):

```bash
python tests/e2e/seed/regenerate_radarr.py
python tests/e2e/seed/regenerate_sonarr.py
```

Each script boots a fresh pinned *arr with the fixed key, configures everything via the v3
API (shared helpers live in `_seed_common.py`), then snapshots `config.xml` + the app DB
back into `radarr/` / `sonarr/`. Commit the result. Keep `RADARR_IMAGE` / `SONARR_IMAGE` in
the scripts in sync with the image tags in `tests/e2e/compose.yaml` — the *arrs auto-migrate
the DB forward on boot, but a schema divergence means you should regenerate.
