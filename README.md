# margot

A Discord bot to integrate [Radarr](https://radarr.video/) & [Sonarr](https://sonarr.tv/), allowing commands like !addmovie and !downloads.

### Usage

1. Copy `config.yaml.template` to `$XDG_CONFIG_HOME/margot/config.yaml` and set the necessary values.
2. `pip install margot` (or from source: `pip install git+https://github.com/wthueb/margot.git`)
3. `margot`

### Development

1. `git clone https://github.com/wthueb/margot.git`
2. `cd margot/`
3. `pip install -e .[dev]`
4. `pre-commit install`

Requires Python >=3.10.

### TODO

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
