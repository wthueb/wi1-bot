class Movie:
    def __init__(self, movie_json: dict) -> None:
        self._json = movie_json

        self.title: str = movie_json["title"]
        self.year: int = movie_json["year"]
        self.tmdb_id: int = movie_json["tmdbId"]

        self.full_title = f"{self.title} ({self.year})"

        self.url = f"https://themoviedb.org/movie/{self.tmdb_id}"

        self.imdb_id: str = ""

        try:
            self.imdb_id = movie_json["imdbId"]
            self.url = f"https://imdb.com/title/{self.imdb_id}"
        except KeyError:
            pass

    def __str__(self) -> str:
        return f"[{self.full_title}]({self.url})"

    def __repr__(self) -> str:
        return str(self.__dict__)
