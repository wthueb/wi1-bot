from pathlib import Path
from shutil import rmtree
from urllib.parse import urlparse

from pyarr import Radarr as RadarrClient
from pyarr.types import JsonArray, JsonObject

from wi1_bot.arr.config import ArrConfig

from .common import Download, ImportMode, MediaState
from .movie import Movie

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
        """Classify a looked-up movie as ABSENT, MONITORED, or DOWNLOADED.

        When Radarr already tracks a movie, lookup returns the library record itself
        (this is what :meth:`lookup_library` filters on), so ``id``, ``movieFileId``
        and ``monitored`` are all in the lookup result — no extra API calls. Don't use
        ``hasFile`` here: only the ``/movie`` controller populates it (from
        statistics), so lookup results always report it null/false.
        """
        if "id" not in movie.json:
            return MediaState.ABSENT

        if movie.json.get("movieFileId", 0) > 0:
            return MediaState.DOWNLOADED

        if movie.json.get("monitored"):
            return MediaState.MONITORED

        return MediaState.ABSENT

    def create_tag(self, tag: str) -> None:
        self._radarr.tag.create(label=tag)

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

    def get_quota_amount(self, user_id: int) -> int:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return 0

        total = 0

        movies = self._radarr.movie.get()
        assert isinstance(movies, list)

        for movie in movies:
            if tag_id in movie["tags"]:
                total += movie["sizeOnDisk"]

        return total

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

    def is_movie_monitored(self, tmdb_id: int) -> bool:
        movies = self._radarr.movie.get(tmdb_id=tmdb_id)
        assert isinstance(movies, list)

        return bool(movies) and bool(movies[0]["monitored"])

    def rescan_movie(self, movie_id: int) -> None:
        self._radarr.command.execute(name="RescanMovie", movieId=movie_id)

    def refresh_movie(self, movie_id: int) -> None:
        self._radarr.command.execute(name="RefreshMovie", movieIds=[movie_id])

    def search_missing(self) -> None:
        self._radarr.command.execute(name="MissingMoviesSearch")

    def downloaded_movies_scan(self, path: Path, import_mode: ImportMode = ImportMode.AUTO) -> None:
        self._radarr.command.execute(
            name="DownloadedMoviesScan", path=str(path), importMode=import_mode
        )

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

        for tag in tags:
            if str(user_id) in tag["label"]:
                tag_id: int = tag["id"]
                return tag_id

        raise ValueError(f"no tag with the user id {user_id}")
