from shutil import rmtree

from pyarr import SonarrAPI  # type: ignore


class Series:
    def __init__(self, series_json: dict) -> None:
        self.title: str = series_json["title"]
        self.year: int = series_json["year"]
        self.tvdb_id: int = series_json["tvdbId"]
        self.db_id: int = series_json["id"]

        self.full_title = f"{self.title} ({self.year})"

        self.url = f"https://thetvdb.com/dereferrer/series/{self.tvdb_id}"

        self.imdb_id: str = ""

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

    def lookup_series(self, query: str) -> list[Series]:
        # TODO: self._sonarr.lookup_series(query)
        return []

    def lookup_library(self, query: str) -> list[Series]:
        # TODO: self._sonarr.get_series()
        return []

    def get_quality_profile_name(self, profile_id: int):
        profiles = self._sonarr.get_quality_profiles()

        for profile in profiles:
            if profile["id"] == profile_id:
                return profile["name"]

        raise ValueError(f"no quality profile with the id {profile_id}")

    def add_series(self, series: Series, profile: str = "good") -> bool:
        # TODO: self._sonarr.add_series(tvdb_id=)
        return False

    def add_tag(self, series: Series, user_id: int) -> bool:
        series_json: dict = self._sonarr.get_series(series.db_id)

        try:
            tag_id = self._get_tag_for_user(user_id)
        except ValueError:
            return False

        self._add_tag(series_json["id"], tag_id)

        return True

    def del_series(self, series: Series) -> None:
        # TODO: self._sonarr.del_series(id)
        pass

    def get_quota_amount(self, user_id: int) -> int:
        return 0

    #  def get_downloads(self) -> list[Download]:
    #  # TODO: self._sonarr.get_queue()
    #  return []

    def refresh_series(self, series_id: int) -> None:
        self._sonarr.post_command("RefreshSeries", seriesId=series_id)

    def _get_quality_profile(self, label: str) -> int:
        profiles: list[dict] = self._sonarr.get_quality_profiles()

        for profile in profiles:
            if profile["name"].lower() == label.lower():
                return profile["id"]

        raise ValueError(f"no quality profile with the name {label}")

    def _get_tag_for_user(self, user_id: int) -> int:
        tags: list[dict] = self._sonarr.get_tag()

        for tag in tags:
            if str(user_id) in tag["label"]:
                return tag["id"]

        raise ValueError(f"no tag with the user id {user_id}")

    def _add_tag(self, dbid: int, tag_id: int) -> None:
        series: dict = self._sonarr.get_series(dbid)

        series["tags"].append(tag_id)

        self._sonarr.upd_series(series)


if __name__ == "__main__":
    import yaml

    with open("config.yaml", "rb") as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])
    pyarr = sonarr._sonarr
