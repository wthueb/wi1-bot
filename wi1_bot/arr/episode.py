class Episode:
    def __init__(
        self,
        ep_json: dict,
        *,
        series_title: str,
        series_tvdb_id: int,
        series_imdb_id: str,
    ) -> None:
        self._json = ep_json

        self.series_title: str = series_title
        self.season_num: int = ep_json["seasonNumber"]
        self.ep_num: int = ep_json["episodeNumber"]
        self.ep_title: str = ep_json["title"]
        self.air_date: str = ep_json["airDate"]
        self.tvdb_id: int = series_tvdb_id
        self.imdb_id: str = series_imdb_id

        self.full_title: str = (
            f"{self.series_title} S{self.season_num:02d}E{self.ep_num:02d} -"
            f" {self.ep_title}"
        )

        if self.imdb_id:
            self.url = f"https://www.imdb.com/title/{self.imdb_id}"
        else:
            self.url = f"https://www.thetvdb.com/?id={self.tvdb_id}"

    def __str__(self) -> str:
        return f"[{self.full_title}]({self.url})"

    def __repr__(self) -> str:
        return str(self.__dict__)
