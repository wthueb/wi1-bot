from shutil import rmtree
from typing import Any

from pyarr import SonarrAPI

from .download import Download


class Series:
    def __init__(self, series_json: dict[str, Any]) -> None:
        self.json = series_json

        self.title: str = series_json["title"]
        self.year: int = series_json["year"]
        self.tvdb_id: int = series_json["tvdbId"]

        self.db_id: int | None = series_json["id"] if "id" in series_json else None

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


class SonarrError(Exception):
    pass


class Sonarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._sonarr = SonarrAPI(url, api_key)

    def lookup_series(self, query: str) -> list[Series]:
        possible_series = self._sonarr.lookup_series(query)

        if isinstance(possible_series, dict):
            raise SonarrError(possible_series["message"])

        return [Series(s) for s in possible_series]

    def lookup_library(self, query: str) -> list[Series]:
        possible_series = self._sonarr.lookup_series(query)

        return [Series(s) for s in possible_series if "id" in s]

    def lookup_user_library(self, query: str, user_id: int) -> list[Series]:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return []

        possible_series = self._sonarr.lookup_series(query)

        # self._sonarr.get_tag_detail is broken/not supported in v1 sonarr API so have
        # to filter the tmdb lookup (probably slower but saves an API call)
        user_series = [s for s in possible_series if tag_id in s["tags"]]

        return [Series(s) for s in user_series]

    def add_series(self, series: Series, profile: str = "good") -> bool:
        if series.db_id is not None:
            return False

        quality_profile_id = self._get_quality_profile_id(profile)
        language_profile_id = self._sonarr.get_language_profile()[0]["id"]
        root_folder = self._sonarr.get_root_folder()
        assert isinstance(root_folder, list)
        root_folder_path = root_folder[0]["path"]

        series_json = self._sonarr.add_series(
            series.json,
            quality_profile_id=quality_profile_id,
            language_profile_id=language_profile_id,
            root_dir=root_folder_path,
            search_for_missing_episodes=True,
        )

        series.db_id = series_json["id"]

        return True

    def del_series(self, series: Series) -> None:
        if series.db_id is None:
            raise ValueError(f"{series} is not in the library")

        series_json = self._sonarr.get_series(series.db_id)
        assert isinstance(series_json, dict)

        self._sonarr.del_series(series.db_id, delete_files=True)

        try:
            rmtree(series_json["path"])
        except FileNotFoundError:
            pass

    def series_downloaded(self, series: Series) -> bool:
        if series.db_id is None:
            return False

        files = self._sonarr.get_episode_files_by_series_id(series.db_id)

        if files:
            return True

        return False

    def create_tag(self, tag: str) -> None:
        self._sonarr.create_tag(tag)

    def add_tag(self, series: Series, user_id: int) -> bool:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            # tag_id = self._radarr.create_tag(str(user_id))['id']

            return False

        series_json = self._sonarr.get_series(series.db_id)
        assert isinstance(series_json, dict)

        series_json["tags"].append(tag_id)

        self._sonarr.upd_series(series_json)

        return True

    def get_downloads(self) -> list[Download]:
        queue = self._sonarr.get_queue(
            page=1,
            page_size=100,
            sort_key="timeleft",
            sort_dir="ascending",
            include_unknown_series_items=False,
        )["records"]

        seen: set[str] = set()
        downloads: list[Download] = []

        for item in queue:
            d = Download(item)

            # dedupe in the case of season packs
            if str(d.content) in seen:
                continue

            seen.add(str(d.content))
            downloads.append(d)

            if len(downloads) >= 10:
                break

        return downloads

    def get_quota_amount(self, user_id: int) -> int:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return 0

        total = 0

        for series in self._sonarr.get_series():
            assert isinstance(series, dict)
            if tag_id in series["tags"]:
                total += series["statistics"]["sizeOnDisk"]

        return total

    def get_quality_profile_name(self, profile_id: int) -> str:
        profiles = self._sonarr.get_quality_profile()

        for profile in profiles:
            if profile["id"] == profile_id:
                name = profile["name"]
                assert isinstance(name, str)
                return name

        raise ValueError(f"no quality profile with the id {profile_id}")

    def get_series(self) -> list[dict[str, Any]]:
        series = self._sonarr.get_series()
        assert isinstance(series, list)
        return series

    def rescan_series(self, series_id: int) -> None:
        self._sonarr.post_command("RescanSeries", seriesId=series_id)  # type: ignore

    def _get_quality_profile_id(self, name: str) -> int:
        profiles = self._sonarr.get_quality_profile()

        for profile in profiles:
            if profile["name"].lower() == name.lower():
                profile_id = profile["id"]
                assert isinstance(profile_id, int)
                return profile_id

        raise ValueError(f"no quality profile with the name {name}")

    def _get_tag_for_user_id(self, user_id: int) -> int:
        tags = self._sonarr.get_tag()
        assert isinstance(tags, list)

        for tag in tags:
            if str(user_id) in tag["label"]:
                tag_id = tag["id"]
                assert isinstance(tag_id, int)
                return tag_id

        raise ValueError(f"no tag with the user id {user_id}")
