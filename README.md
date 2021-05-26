# wi1-bot

a discord bot to integrate radarr and transmission, allowing commands like !addmovie and !downloads

TODO:

- !rate / !ratings
    - store in some sort of database
    - !movierec based off of ratings and similar-to-user ratings?
        - https://towardsdatascience.com/the-4-recommendation-engines-that-can-predict-your-movie-tastes-109dc4e10c52
    - !linkimdb: probably the easiest solution
- !movieinfo showing ratings/other general info
    - use radarr get_movie api
    - tautulli get_history api to see who has already seen?
    - if !linkimdb, then can see other user's ratings
- movie leaderboard
    - tautulli get_history api?
