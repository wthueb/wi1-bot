# wi1-bot

Integrates [Radarr](https://radarr.video/) & [Sonarr](https://sonarr.tv/) with Discord
(commands like `!addmovie`, `!downloads`) and transcodes downloads with ffmpeg.

It is a [uv](https://docs.astral.sh/uv/) workspace of five packages — two shared
libraries and three independently deployable services (each with its own config file
and Docker image):

| Package | Import | What it is |
|---|---|---|
| `common` | `wi1_bot.common` | shared logging + pushover helpers (library) |
| `arr` | `wi1_bot.arr` | Radarr/Sonarr (pyarr) wrapper (library) |
| `wi1-bot` | `wi1_bot.bot` | the Discord bot → image `wthueb/wi1-bot` |
| `webhook` | `wi1_bot.webhook` | Radarr/Sonarr download webhook; owns the transcode queue and dispatches jobs → image `wthueb/wi1-bot-webhook` |
| `transcoder` | `wi1_bot.transcoder` | replicable ffmpeg worker that pulls jobs from the webhook → image `wthueb/wi1-bot-transcoder` |

The three services all share one top-level `wi1_bot` namespace but ship as separate
distributions, so each image only contains the code (and dependencies) it needs.
Transcode workers claim leased jobs from the webhook over HTTP and can be scaled out
(`docker compose up -d --scale wi1-bot-transcoder=3`).

### Usage (Docker)

1. Copy each service's `config.yaml.template` to its own config directory and fill it in:
   - `wi1-bot/config.yaml.template` → `bot/config.yaml`
   - `webhook/config.yaml.template` → `webhook/config.yaml`
   - `transcoder/config.yaml.template` → `transcoder/config.yaml`
2. Point Radarr/Sonarr's connect webhook at the webhook service (`http://<host>:9000/`).
3. `docker compose up -d` (edit `compose.yaml` for the media mount and GPU as needed).

### Development

1. `git clone https://github.com/wthueb/wi1-bot.git`
2. `cd wi1-bot/`
3. `uv sync`
4. `uv run pre-commit install`

Run a service locally with its config: `WB_CONFIG_PATH=… uv run wi1-bot-webhook`
(likewise `wi1-bot`, `wi1-bot-transcoder`). Tests/type-check: `uv run pytest`,
`uv run ty check`. Requires Python >=3.12.

### TODO

- use seerr for search/requests
  - !link discord user to seerr user
- fix ty errors, avoiding ignore comments where possible
- figure out qsv codecs
  - also maybe software encoders?
- maybe check languages and things on new downloads via webhook
- notify on manual import required?
- transcode avis
- integration testing
  - https://pypi.org/project/pytest-docker/
- web dashboard? django i guess?
  - transcode queue, transcode progress, quotas
  - reactivity would be nice, maybe htmx/alpinejs?
    - https://www.mattlayman.com/blog/2021/how-to-htmx-django/
- ffmpeg filters for deinterlacing, scaling
  - https://docs.nvidia.com/video-technologies/video-codec-sdk/12.0/ffmpeg-with-nvidia-gpu/index.html#hwaccel-transcode-with-scaling
- have config.discord.users be a dict with 'quotas' and 'name' for *arr tags
- Better pushover notifications
  - Failures for pretty much everything
  - Notifications for grabs/downloads of personal watchlist
- Tag user who added movie when it's downloaded
  - Would replace Radarr/Sonarr's Discord webhooks
  - !notify \<query\> to also be tagged when a movie/show someone else added is downloaded
    - react to "added movie/show" instead of having to !notify
    - react to notification to stop notifications
    - if user tries to add movie that's already present, add them to list to notify
    - Would require a DB; don't use tags as those are to strictly track quotas
      - DB is useful for caching other information as well
- Use Discord slash commands instead of normal text commands
  - This is difficult/impossible currently, can't have "conversation" with slash commands
- Enforce quotas
- !linktmdb
  - !rate / !ratings (https://developers.themoviedb.org/3/movies/rate-movie)
  - !movierec based off of ratings and similar-to-user ratings?
    - https://towardsdatascience.com/the-4-recommendation-engines-that-can-predict-your-movie-tastes-109dc4e10c52
    - or just use TMDB's API to get recommendations (if that's possible?)
- !movieinfo showing user/public ratings and other general info (runtime, cast, director)
  - use TMDB API to get movie metadata
  - if movie isn't on Radarr, react to message to add it?
  - Tautulli API (get_history) to show who has already seen the movie
- User leaderboard
  - movies/shows added, Tautulli watch counts
