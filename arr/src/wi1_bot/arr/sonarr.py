from collections import defaultdict
from collections.abc import Iterable
from shutil import rmtree
from urllib.parse import urlparse

from pyarr import PyarrBadRequest, PyarrResourceNotFound
from pyarr import Sonarr as SonarrClient
from pyarr.types import JsonArray, JsonObject

from wi1_bot.arr.config import ArrConfig

from .common import Download, MediaState, user_id_from_tag
from .episode import Episode
from .queue import ArrQueueItem, ArrQueueItemNotFound, ArrQueuePage
from .release import (
    ReleasePushConfigurationError,
    ReleasePushRequest,
    ReleasePushResult,
    parse_release_push_bad_request,
    validate_release_push_results,
)


class Series:
    def __init__(self, series_json: JsonObject) -> None:
        self.json = series_json

        self.title: str = series_json["title"]
        self.year: int = series_json["year"]
        self.tvdb_id: int = series_json["tvdbId"]

        self.db_id: int | None = series_json["id"] if "id" in series_json else None

        self.full_title = f"{self.title} ({self.year})"

        self.url = f"https://thetvdb.com/dereferrer/series/{self.tvdb_id}"

        # prefer an imdb link, but the api can return imdbId as "" as well as omit it
        self.imdb_id: str = series_json.get("imdbId") or ""

        if self.imdb_id:
            self.url = f"https://imdb.com/title/{self.imdb_id}"

    def __str__(self) -> str:
        return f"[{self.full_title}]({self.url})"

    def __repr__(self) -> str:
        return str(self.__dict__)


class SonarrError(Exception):
    pass


class Sonarr:
    @classmethod
    def from_config(cls, config: ArrConfig) -> "Sonarr":
        return Sonarr(str(config.url), config.api_key)

    def __init__(self, url: str, api_key: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 8989)
        tls = parsed.scheme == "https"

        self._sonarr = SonarrClient(
            host=host, api_key=api_key, port=port, tls=tls, base_path=parsed.path
        )

    def lookup_series(self, query: str) -> list[Series]:
        # Note: pyarr v6 raises exceptions on API errors instead of returning error dicts
        possible_series = self._sonarr.series.lookup(term=query)

        return [Series(s) for s in possible_series]

    def lookup_library(self, query: str) -> list[Series]:
        possible_series = self._sonarr.series.lookup(term=query)

        return [Series(s) for s in possible_series if "id" in s]

    def lookup_user_library(self, query: str, user_id: int) -> list[Series]:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return []

        possible_series = self._sonarr.series.lookup(term=query)

        # self._sonarr.tag.get_detail is broken/not supported in v1 sonarr API so have
        # to filter the tvdb lookup (probably slower but saves an API call)
        user_series = [s for s in possible_series if tag_id in s["tags"]]

        return [Series(s) for s in user_series]

    def add_series(self, series: Series, profile: str = "good") -> bool:
        if series.db_id is not None:
            return False

        quality_profile_id = self._get_quality_profile_id(profile)

        root_folder = self._sonarr.root_folder.get()
        assert isinstance(root_folder, list)
        root_folder_path: str = root_folder[0]["path"]

        # Note: language_profile_id is deprecated in Sonarr v4, but pyarr still requires it.
        # Using 1 as a default placeholder value.
        series_json = self._sonarr.series.add(
            series=series.json,
            quality_profile_id=quality_profile_id,
            language_profile_id=1,
            root_dir=root_folder_path,
            search_for_missing_episodes=True,
        )

        series.db_id = series_json["id"]

        return True

    def del_series(self, series: Series) -> None:
        if series.db_id is None:
            raise ValueError(f"{series} is not in the library")

        series_json = self._sonarr.series.get(item_id=series.db_id)
        assert isinstance(series_json, dict)

        self._sonarr.series.delete(item_id=series.db_id, delete_files=True)

        try:
            rmtree(series_json["path"])
        except FileNotFoundError:
            pass

    def series_downloaded(self, series: Series) -> bool:
        if series.db_id is None:
            return False

        files = self._sonarr.episode_file.get(series_id=series.db_id)
        assert isinstance(files, list)

        return len(files) > 0

    def series_state(self, series: Series) -> MediaState:
        if series.db_id is None:
            return MediaState.ABSENT

        if self.get_series_by_id(series.db_id)["statistics"]["episodeFileCount"] > 0:
            return MediaState.DOWNLOADED

        if series.json.get("monitored"):
            return MediaState.MONITORED

        return MediaState.ABSENT

    def create_tag(self, tag: str) -> None:
        self._sonarr.tag.create(label=tag)

    def get_tags(self) -> list[str]:
        tags = self._sonarr.tag.get()
        assert isinstance(tags, list)
        return [tag["label"] for tag in tags]

    def add_tag(self, series: Series, user_id: int) -> bool:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            # tag_id = self._sonarr.tag.create(label=str(user_id))['id']

            return False

        series_json = self._sonarr.series.get(item_id=series.db_id)
        assert isinstance(series_json, dict)

        series_json["tags"].append(tag_id)

        self._sonarr.series.update(data=series_json)

        return True

    def get_downloads(self) -> list[Download]:
        queue = self._sonarr.queue.get(
            page=1,
            page_size=100,
            sort_key="timeleft",
            sort_dir="ascending",
            include_series=True,
            include_episode=True,
        )
        records: JsonArray = queue.get("records", [])

        seen: set[str] = set()
        downloads: list[Download] = []

        for item in records:
            d = Download(item)

            # dedupe in the case of season packs
            if str(d.content) in seen:
                continue

            seen.add(str(d.content))
            downloads.append(d)

            if len(downloads) >= 10:
                break

        return downloads

    def get_queue_items(self, page_size: int = 100) -> list[ArrQueueItem]:
        items: list[ArrQueueItem] = []
        page_number = 1

        while True:
            response = self._sonarr.queue.get(page=page_number, page_size=page_size)
            page = ArrQueuePage.model_validate(response)
            items.extend(page.records)

            if not page.records:
                break
            if page.total_records is not None and len(items) >= page.total_records:
                break
            if len(page.records) < page_size:
                break
            page_number += 1

        return items

    def remove_queue_item(self, item_id: int, *, remove_from_client: bool) -> None:
        try:
            self._sonarr.queue.delete(
                item_id,
                remove_from_client=remove_from_client,
                blocklist=False,
            )
        except PyarrResourceNotFound as exc:
            raise ArrQueueItemNotFound(item_id) from exc

    def get_quota_amount(self, user_id: int) -> int:
        return self.get_quota_amounts([user_id])[user_id]

    def get_quota_amounts(self, user_ids: Iterable[int]) -> dict[int, int]:
        user_ids = set(user_ids)

        tags = self._sonarr.tag.get()
        assert isinstance(tags, list)
        tag_for_user: dict[int, int] = {}
        for uid in user_ids:
            tag_for_user[uid] = next(
                (tag["id"] for tag in tags if user_id_from_tag(tag["label"]) == uid), -1
            )

        size_for_tag: dict[int, int] = defaultdict(int)

        all_series = self._sonarr.series.get()
        assert isinstance(all_series, list)

        for s in all_series:
            for tag_id in s["tags"]:
                size_for_tag[tag_id] += s["statistics"]["sizeOnDisk"]

        return {uid: size_for_tag[tag_for_user[uid]] for uid in user_ids}

    def get_tag_title_counts(self) -> dict[str, int]:
        # sonarr's tag detail carries no seriesIds, so counts come from one series scan
        tags = self._sonarr.tag.get()
        assert isinstance(tags, list)

        if not tags:
            return {}

        label_for_id: dict[int, str] = {tag["id"]: tag["label"] for tag in tags}
        counts: dict[str, int] = dict.fromkeys(label_for_id.values(), 0)

        all_series = self._sonarr.series.get()
        assert isinstance(all_series, list)

        for s in all_series:
            for tag_id in s["tags"]:
                label = label_for_id.get(tag_id)
                if label is not None:
                    counts[label] += 1

        return counts

    def downloaded_episodes_by_tvdb_id(self, tvdb_ids: Iterable[int]) -> dict[int, list[Episode]]:
        wanted = set(tvdb_ids)
        if not wanted:
            return {}

        all_series = self._sonarr.series.get()
        assert isinstance(all_series, list)

        result: dict[int, list[Episode]] = {}

        for s in all_series:
            tvdb_id: int = s["tvdbId"]
            if tvdb_id not in wanted:
                continue

            result[tvdb_id] = []

            if (s.get("statistics") or {}).get("episodeFileCount", 0) == 0:
                continue

            episodes = self._sonarr.episode.get(series_id=s["id"])
            assert isinstance(episodes, list)

            result[tvdb_id] = [
                Episode(
                    ep,
                    series_title=s["title"],
                    series_tvdb_id=tvdb_id,
                    series_imdb_id=s.get("imdbId") or "",
                )
                for ep in episodes
                if ep.get("hasFile")
            ]

        return result

    def downloaded_series_tvdb_ids(self) -> set[int]:
        all_series = self._sonarr.series.get()
        assert isinstance(all_series, list)

        return {
            s["tvdbId"]
            for s in all_series
            if (s.get("statistics") or {}).get("episodeFileCount", 0) > 0
        }

    def get_quality_profile_name(self, profile_id: int) -> str:
        profiles = self._sonarr.quality_profile.get()
        assert isinstance(profiles, list)

        for profile in profiles:
            if profile["id"] == profile_id:
                name: str = profile["name"]
                return name

        raise ValueError(f"no quality profile with the id {profile_id}")

    def get_root_folders(self) -> JsonArray:
        root_folders = self._sonarr.root_folder.get()
        assert isinstance(root_folders, list)
        return root_folders

    def get_series(self) -> JsonArray:
        series = self._sonarr.series.get()
        assert isinstance(series, list)
        return series

    def get_episode_files(self, series_id: int) -> JsonArray:
        episode_files = self._sonarr.episode_file.get(series_id=series_id)
        assert isinstance(episode_files, list)
        return episode_files

    def get_series_by_id(self, series_id: int) -> JsonObject:
        series = self._sonarr.series.get(item_id=series_id)
        assert isinstance(series, dict)
        return series

    def push_release(self, release: ReleasePushRequest) -> list[ReleasePushResult]:
        try:
            response = self._sonarr.release.handler.request(
                "release/push",
                method="POST",
                json_data=release.as_arr_payload(),
            )
        except PyarrBadRequest as exc:
            rejections, invalid_download_client = parse_release_push_bad_request(str(exc))
            if invalid_download_client:
                raise ReleasePushConfigurationError(
                    "sonarr push has invalid download client configuration"
                ) from exc
            return [
                ReleasePushResult(
                    approved=False,
                    rejected=True,
                    temporarilyRejected=False,
                    rejections=rejections,
                )
            ]
        return validate_release_push_results(response)

    def rescan_series(self, series_id: int) -> None:
        self._sonarr.command.execute(name="RescanSeries", seriesId=series_id)

    def _get_quality_profile_id(self, name: str) -> int:
        profiles = self._sonarr.quality_profile.get()
        assert isinstance(profiles, list)

        for profile in profiles:
            if profile["name"].lower() == name.lower():
                profile_id: int = profile["id"]
                return profile_id

        raise ValueError(f"no quality profile with the name {name}")

    def _get_tag_for_user_id(self, user_id: int) -> int:
        tags = self._sonarr.tag.get()
        assert isinstance(tags, list)

        for tag in tags:
            if user_id_from_tag(tag["label"]) == user_id:
                tag_id: int = tag["id"]
                return tag_id

        raise ValueError(f"no tag with the user id {user_id}")
