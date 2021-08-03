class Movie:
    def __init__(self, movie_json: dict) -> None:
        self.title = movie_json['title']
        self.year = movie_json['year']
        self.tmdb_id = movie_json['tmdbId']

        self.full_title = f'{self.title} ({self.year})'
        self.url = f'https://themoviedb.org/movie/{self.tmdb_id}'

    def __str__(self) -> str:
        return f'[{self.full_title}]({self.url})'

    def __repr__(self) -> str:
        return str(self.__dict__)
