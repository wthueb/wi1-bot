# wi1-bot

a discord bot to integrate radarr and transmission, allowing commands like !addmovie and !downloads

TODO:

- !linktmdb
- !rate / !ratings
    - store using tmdb api https://developers.themoviedb.org/3/movies/rate-movie
    - !movierec based off of ratings and similar-to-user ratings?
        - https://towardsdatascience.com/the-4-recommendation-engines-that-can-predict-your-movie-tastes-109dc4e10c52
        - or just use tmdb's api to get recommendations
- !movieinfo showing user/public ratings and other general info (runtime, cast, director)
    - use tmdb api
    - support not having movie on radarr and adding it
    - tautulli get_history api to show who has already seen the movie
- movie leaderboard
    - tautulli get_history api
