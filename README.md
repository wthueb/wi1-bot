# wi1-bot

A Discord bot to integrate Radarr (with plans for Sonarr as well), allowing commands like !addmovie and !downloads.

TODO:

- Proper configuration file (PyYAML?)
- Automatically transcode movie downloads to user-defined quality
- Allow user to delete movies that they have added
- Actually enforce download quotas
- Add Sonarr support — !addshow
- !linktmdb
    - !rate / !ratings (https://developers.themoviedb.org/3/movies/rate-movie)
    - !movierec based off of ratings and similar-to-user ratings?
        - https://towardsdatascience.com/the-4-recommendation-engines-that-can-predict-your-movie-tastes-109dc4e10c52
        - or just use TMDB's API to get recommendations (if that's possible?)
- !movieinfo showing user/public ratings and other general info (runtime, cast, director)
    - Use TMDB API to get movie metadata
    - If movie isn't on Radarr, react to message to add it?
    - Tautulli API (get_history) to show who has already seen the movie
- User leaderboard
