from collections import defaultdict
from collections.abc import Iterable
from shutil import rmtree
from urllib.parse import urlparse

from pyarr import PyarrBadRequest, PyarrResourceNotFound
from pyarr import Radarr as RadarrClient
from pyarr.types import JsonArray, JsonObject

from wi1_bot.arr.config import ArrConfig

from .common import Download, MediaState, user_id_from_tag
from .movie import Movie
from .queue import ArrQueueItem, ArrQueueItemNotFound, ArrQueuePage
from .release import (
    ReleasePushConfigurationError,
    ReleasePushRequest,
    ReleasePushResult,
    parse_release_push_bad_request,
    validate_release_push_results,
)

__all__ = ["Movie", "Radarr"]


class Radarr:
    @classmethod
    def from_config(cls, config: ArrConfig) -> "Radarr":
        return Radarr(str(config.url), config.api_key)

    def __init__(self, url: str, api_key: str) -> None:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or (443 if parsed.scheme == "https" else 7878)
        tls = parsed.scheme == "https"

        self._radarr = RadarrClient(
            host=host, api_key=api_key, port=port, tls=tls, base_path=parsed.path
        )

    def lookup_movie(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.movie.lookup(term=query)
        return [Movie(m) for m in possible_movies]

    def lookup_library(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.movie.lookup(term=query)
        return [Movie(m) for m in possible_movies if "id" in m]

    def lookup_user_library(self, query: str, user_id: int) -> list[Movie]:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return []

        tag_detail = self._radarr.tag.get_detail(item_id=tag_id)
        possible_movies = self._radarr.movie.lookup(term=query)

        user_movie_ids: list[int] = tag_detail["movieIds"]

        return [Movie(m) for m in possible_movies if "id" in m and m["id"] in user_movie_ids]

    def add_movie(self, movie: Movie, profile: str = "good") -> bool:
        existing = self._radarr.movie.get(tmdb_id=movie.tmdb_id)
        if existing:
            return False

        quality_profile_id = self._get_quality_profile_id(profile)

        root_folder = self._radarr.root_folder.get()
        assert isinstance(root_folder, list)
        root_folder_path: str = root_folder[0]["path"]

        self._radarr.movie.add(
            movie=movie.json,
            root_dir=root_folder_path,
            quality_profile_id=quality_profile_id,
        )

        return True

    def del_movie(self, movie: Movie) -> None:
        potential = self._radarr.movie.get(tmdb_id=movie.tmdb_id)
        assert isinstance(potential, list)

        if not potential:
            raise ValueError(f"{movie} is not in the library")

        movie_json: JsonObject = potential[0]

        db_id: int = movie_json["id"]
        path: str = movie_json["folderName"]

        self._radarr.movie.delete(item_id=db_id, delete_files=True, add_exclusion=False)

        try:
            rmtree(path)
        except FileNotFoundError:
            pass

    def movie_downloaded(self, movie: Movie) -> bool:
        potential = self._radarr.movie.get(tmdb_id=movie.tmdb_id)
        assert isinstance(potential, list)

        if not potential:
            return False

        files = self._radarr.movie_file.get(movie_id=potential[0]["id"])

        return len(files) > 0

    def movie_state(self, movie: Movie) -> MediaState:
        if "id" not in movie.json:
            return MediaState.ABSENT

        if movie.json.get("movieFileId", 0) > 0:
            return MediaState.DOWNLOADED

        if movie.json.get("monitored"):
            return MediaState.MONITORED

        return MediaState.ABSENT

    def create_tag(self, tag: str) -> None:
        self._radarr.tag.create(label=tag)

    def get_tags(self) -> list[str]:
        tags = self._radarr.tag.get()
        assert isinstance(tags, list)
        return [tag["label"] for tag in tags]

    def add_tag(self, movie: Movie | list[Movie], user_id: int) -> bool:
        if isinstance(movie, Movie):
            movie = [movie]

        ids: list[int] = []

        for m in movie:
            json = self._radarr.movie.get(tmdb_id=m.tmdb_id)
            assert isinstance(json, list)
            ids.append(json[0]["id"])

        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            # tag_id = self._radarr.tag.create(label=str(user_id))['id']

            return False

        edit_json: JsonObject = {"movieIds": ids, "tags": [tag_id], "applyTags": "add"}

        self._radarr.movie.handler.request("movie/editor", method="PUT", json_data=edit_json)

        return True

    def get_downloads(self) -> list[Download]:
        queue = self._radarr.queue.get(include_movie=True)
        records: JsonArray = queue.get("records", [])

        downloads = [Download(d) for d in records]

        return sorted(downloads, key=lambda d: (d.timeleft, -d.pct_done))

    def get_queue_items(self, page_size: int = 100) -> list[ArrQueueItem]:
        items: list[ArrQueueItem] = []
        page_number = 1

        while True:
            response = self._radarr.queue.get(page=page_number, page_size=page_size)
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
            self._radarr.queue.delete(
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

        tags = self._radarr.tag.get()
        tag_for_user: dict[int, int] = {}
        for uid in user_ids:
            tag_for_user[uid] = next(
                (tag["id"] for tag in tags if user_id_from_tag(tag["label"]) == uid), -1
            )

        size_for_tag: dict[int, int] = defaultdict(int)

        movies = self._radarr.movie.get()
        assert isinstance(movies, list)

        for movie in movies:
            for tag_id in movie["tags"]:
                size_for_tag[tag_id] += movie["sizeOnDisk"]

        return {uid: size_for_tag[tag_for_user[uid]] for uid in user_ids}

    def get_tag_title_counts(self) -> dict[str, int]:
        details = self._radarr.tag.get_detail()
        assert isinstance(details, list)

        return {detail["label"]: len(detail["movieIds"]) for detail in details}

    def downloaded_movie_tmdb_ids(self) -> set[int]:
        movies = self._radarr.movie.get()
        assert isinstance(movies, list)

        return {movie["tmdbId"] for movie in movies if movie.get("hasFile")}

    def get_quality_profile_name(self, profile_id: int) -> str:
        profiles = self._radarr.quality_profile.get()
        assert isinstance(profiles, list)

        for profile in profiles:
            if profile["id"] == profile_id:
                name: str = profile["name"]
                return name

        raise ValueError(f"no quality profile with the id {profile_id}")

    def get_movies(self) -> JsonArray:
        movies = self._radarr.movie.get()
        assert isinstance(movies, list)
        return movies

    def get_movie_by_id(self, movie_id: int) -> JsonObject:
        movie = self._radarr.movie.get(item_id=movie_id)
        assert isinstance(movie, dict)
        return movie

    def get_movie_credits(self, movie_id: int) -> JsonArray:
        credits = self._radarr.movie.handler.request("credit", params={"movieId": movie_id})
        assert isinstance(credits, list)
        return credits

    def push_release(self, release: ReleasePushRequest) -> list[ReleasePushResult]:
        try:
            response = self._radarr.release.handler.request(
                "release/push",
                method="POST",
                json_data=release.as_arr_payload(),
            )
        except PyarrBadRequest as exc:
            rejections, invalid_download_client = parse_release_push_bad_request(str(exc))
            if invalid_download_client:
                raise ReleasePushConfigurationError(
                    "radarr push has invalid download client configuration"
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

    def rescan_movie(self, movie_id: int) -> None:
        self._radarr.command.execute(name="RescanMovie", movieId=movie_id)

    def refresh_movie(self, movie_id: int) -> None:
        self._radarr.command.execute(name="RefreshMovie", movieIds=[movie_id])

    def search_missing(self) -> None:
        self._radarr.command.execute(name="MissingMoviesSearch")

    def _get_quality_profile_id(self, name: str) -> int:
        profiles = self._radarr.quality_profile.get()
        assert isinstance(profiles, list)

        for profile in profiles:
            if profile["name"].lower() == name.lower():
                profile_id: int = profile["id"]
                return profile_id

        raise ValueError(f"no quality profile with the name {name}")

    def _get_tag_for_user_id(self, user_id: int) -> int:
        tags = self._radarr.tag.get()
        assert isinstance(tags, list)

        for tag in tags:
            if user_id_from_tag(tag["label"]) == user_id:
                tag_id: int = tag["id"]
                return tag_id

        raise ValueError(f"no tag with the user id {user_id}")
