from .episode import Episode
from .movie import Movie


class Download:
    def __init__(self, data: dict) -> None:
        self.content: Movie | Episode | str

        if "movie" in data:
            self.content = Movie(data["movie"])
        elif "episode" in data:
            title = data["series"]["title"]
            tvdb_id = data["series"]["tvdbId"] if "tvdbId" in data["series"] else 0
            imdb_id = data["series"]["imdbId"] if "imdbId" in data["series"] else ""

            self.content = Episode(
                data["episode"],
                series_title=title,
                series_tvdb_id=tvdb_id,
                series_imdb_id=imdb_id,
            )
        else:
            self.content = data["title"]

        self.sizeleft = data["sizeleft"]
        self.size = data["size"]
        self.timeleft = data["timeleft"] if "timeleft" in data else "unknown"
        self.status = data["status"]

        self.pct_done = (self.size - self.sizeleft) / self.size * 100

    def __str__(self) -> str:
        downloaded = (self.size - self.sizeleft) / 1024**3
        total = self.size / 1024**3

        return (
            f"{self.content}: {self.pct_done:.1f}% done"
            f" ({downloaded:.2f}/{total:.2f} GB)\neta: {self.timeleft}"
        )

    def __repr__(self) -> str:
        return str(self.__dict__)
