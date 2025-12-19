# wi1-bot

A Discord bot to integrate [Radarr](https://radarr.video/) & [Sonarr](https://sonarr.tv/), allowing commands like !addmovie and !downloads.

### Usage

1. Copy `config.yaml.template` to `$XDG_CONFIG_HOME/wi1-bot/config.yaml` and set the necessary values.
2. `pip install wi1-bot` (or from source: `pip install git+https://github.com/wthueb/wi1-bot.git`)
3. `wi1-bot`

### Development

1. `git clone https://github.com/wthueb/wi1-bot.git`
2. `cd wi1-bot/`
3. `pip install -e .[dev]`
4. `pre-commit install`

Requires Python >=3.11.

### TODO

- fix basedpyright errors, avoiding ignore comments where possible
- multiple transcode workers
  - main server instance (as part of the existing webhook server, rename to api?). core app wouldn't be running transcoder anymore
  - worker nodes that point at the main server instance and use REST calls to get jobs and update job statuses
    - separate docker image
    - configure transcoding settings for each profile on each instance
    - if job fails, retry once on every instance before error notification
- figure out qsv codecs
  - also maybe software encoders?
- maybe check languages and things on new downloads via webhook
- notify on manual import required?
- transcode avis
- integration testing
  - https://pypi.org/project/pytest-docker/
- use overseerr for search/requests
- web dashboard? django i guess?
  - transcode queue, transcode progress, quotas
  - reactivity would be nice, maybe htmx/alpinejs?
    - https://www.mattlayman.com/blog/2021/how-to-htmx-django/
- link discord user to overseerr user
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
