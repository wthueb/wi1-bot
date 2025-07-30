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

- use overseerr for search/requests
- use sqlite
- dynamically copy streams
  - i.e. if mov_text in input, -c:s srt
  - https://github.com/HaveAGitGat/Tdarr_Plugins/blob/aef12f3c65905f5fc7d045b1a96ddc6a58dc55e7/FlowPluginsTs/CommunityFlowPlugins/ffmpegCommand/ffmpegCommandSetContainer/1.0.0/index.ts#L77
- https://docs.docker.com/build/ci/github-actions/multi-platform/#distribute-build-across-multiple-runners
- link discord user to overseerr user
- https://github.com/kkroening/ffmpeg-python
  - `ffmpeg -codecs`, `ffmpeg -hwaccels`
- ffmpeg filters for deinterlacing, scaling
  - https://docs.nvidia.com/video-technologies/video-codec-sdk/12.0/ffmpeg-with-nvidia-gpu/index.html#hwaccel-transcode-with-scaling
- ffmpeg remove bad subtitle streams
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
- Testing
  - docker(-compose) for spinning up Sonarr and Radarr instances to test API interactions
- Web dashboard for seeing transcode queue, transcode progress, quotas
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
