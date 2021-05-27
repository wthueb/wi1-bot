# wi1-bot

a discord bot to integrate radarr and transmission, allowing commands like !addmovie and !downloads

TODO:

- !linktmdb
- !rate / !ratings
    - store using tmdb api https://developers.themoviedb.org/3/movies/rate-movie
    - !movierec based off of ratings and similar-to-user ratings?
        - https://towardsdatascience.com/the-4-recommendation-engines-that-can-predict-your-movie-tastes-109dc4e10c52
- !movieinfo showing ratings/other general info
    - use radarr get_movie api (or just tmdb api)
    - tautulli get_history api to see who has already seen?
    - see other users' ratings
- movie leaderboard
    - tautulli get_history api?
