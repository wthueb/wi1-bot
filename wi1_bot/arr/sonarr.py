from pyarr import SonarrAPI

from .download import Download


class Series:
    def __init__(self, series_json: dict) -> None:
        self.title: str = series_json["title"]
        self.year: int = series_json["year"]
        self.tvdb_id: int = series_json["tvdbId"]
        self.db_id: int = series_json["id"]

        self.full_title = f"{self.title} ({self.year})"

        self.url = f"https://thetvdb.com/dereferrer/series/{self.tvdb_id}"

        self.imdb_id = ""

        try:
            self.imdb_id = series_json["imdbId"]
            self.url = f"https://imdb.com/title/{self.imdb_id}"
        except KeyError:
            pass

    def __str__(self) -> str:
        return f"[{self.full_title}]({self.url})"

    def __repr__(self) -> str:
        return str(self.__dict__)


class Sonarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._sonarr = SonarrAPI(url, api_key)

    def get_downloads(self) -> list[Download]:
        queue = self._sonarr.get_queue()

        downloads = [Download(d) for d in queue]

        return downloads

    def get_quota_amount(self, user_id: int) -> int:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return 0

        total = 0

        for series in self._sonarr.get_series():
            if tag_id in series["tags"]:
                total += series["sizeOnDisk"]

        return total

    def get_quality_profile_name(self, profile_id: int):
        profiles = self._sonarr.get_quality_profile()

        for profile in profiles:
            if profile["id"] == profile_id:
                return profile["name"]

        raise ValueError(f"no quality profile with the id {profile_id}")

    def rescan_series(self, series_id: int) -> None:
        self._sonarr.post_command("RescanSeries", seriesId=series_id)

    def _get_tag_for_user_id(self, user_id: int) -> int:
        tags = self._sonarr.get_tag()

        for tag in tags:
            if str(user_id) in tag["label"]:
                return tag["id"]

        raise ValueError(f"no tag with the user id {user_id}")
