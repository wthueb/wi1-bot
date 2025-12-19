from shutil import rmtree
from typing import Any

from pyarr import RadarrAPI

from .download import Download
from .movie import Movie

__all__ = ["Movie", "Radarr"]


class Radarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._radarr = RadarrAPI(url, api_key)

    def lookup_movie(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.lookup_movie(query)

        return [Movie(m) for m in possible_movies]

    def lookup_library(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.lookup_movie(query)

        return [Movie(m) for m in possible_movies if "id" in m]

    def lookup_user_library(self, query: str, user_id: int) -> list[Movie]:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return []

        tag_detail = self._radarr.get_tag_detail(tag_id)
        assert isinstance(tag_detail, dict)

        possible_movies = self._radarr.lookup_movie(query)

        user_movie_ids = tag_detail["movieIds"]

        return [Movie(m) for m in possible_movies if "id" in m and m["id"] in user_movie_ids]

    def add_movie(self, movie: Movie, profile: str = "good") -> bool:
        if self._radarr.get_movie(movie.tmdb_id, tmdb=True):
            return False

        quality_profile_id = self._get_quality_profile_id(profile)

        root_folder = self._radarr.get_root_folder()
        assert isinstance(root_folder, list)
        root_folder_path = root_folder[0]["path"]

        self._radarr.add_movie(
            movie.json,
            root_dir=root_folder_path,
            quality_profile_id=quality_profile_id,
        )

        return True

    def del_movie(self, movie: Movie) -> None:
        potential = self._radarr.get_movie(movie.tmdb_id, tmdb=True)
        assert isinstance(potential, list)

        if not potential:
            raise ValueError(f"{movie} is not in the library")

        movie_json = potential[0]

        db_id = movie_json["id"]
        path = movie_json["folderName"]

        self._radarr.del_movie(db_id, delete_files=True, add_exclusion=False)

        try:
            rmtree(path)
        except FileNotFoundError:
            pass

    def movie_downloaded(self, movie: Movie) -> bool:
        potential = self._radarr.get_movie(movie.tmdb_id, tmdb=True)
        assert isinstance(potential, list)

        if not potential:
            return False

        files = self._radarr.get_movie_files_by_movie_id(potential[0]["id"])

        return len(files) > 0

    def create_tag(self, tag: str) -> None:
        self._radarr.create_tag(tag)

    def add_tag(self, movie: Movie | list[Movie], user_id: int) -> bool:
        if isinstance(movie, Movie):
            json = self._radarr.get_movie(movie.tmdb_id, tmdb=True)
            assert isinstance(json, list)
            ids = [json[0]["id"]]
        else:
            ids = []

            for m in movie:
                json = self._radarr.get_movie(m.tmdb_id, tmdb=True)
                assert isinstance(json, list)
                ids.append(json[0]["id"])

        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            # tag_id = self._radarr.create_tag(str(user_id))['id']

            return False

        edit_json = {"movieIds": ids, "tags": [tag_id], "applyTags": "add"}

        self._radarr.upd_movies(edit_json)

        return True

    def get_downloads(self) -> list[Download]:
        queue = self._radarr.get_queue_details()

        downloads = [Download(d) for d in queue]

        return sorted(downloads, key=lambda d: (d.timeleft, -d.pct_done))

    def get_quota_amount(self, user_id: int) -> int:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return 0

        total = 0

        for movie in self._radarr.get_movie():
            assert isinstance(movie, dict)

            if tag_id in movie["tags"]:
                total += movie["sizeOnDisk"]

        return total

    def get_quality_profile_name(self, profile_id: int) -> str:
        profiles = self._radarr.get_quality_profile()

        for profile in profiles:
            if profile["id"] == profile_id:
                name = profile["name"]
                assert isinstance(name, str)
                return name

        raise ValueError(f"no quality profile with the id {profile_id}")

    def get_movies(self) -> list[dict[str, Any]]:
        movies = self._radarr.get_movie()
        assert isinstance(movies, list)
        return movies

    def rescan_movie(self, movie_id: int) -> None:
        self._radarr.post_command("RescanMovie", movieId=movie_id)  # type: ignore

    def refresh_movie(self, movie_id: int) -> None:
        self._radarr.post_command("RefreshMovie", movieIds=[movie_id])  # type: ignore

    def search_missing(self) -> None:
        self._radarr.post_command(name="MissingMoviesSearch")

    def _get_quality_profile_id(self, name: str) -> int:
        profiles = self._radarr.get_quality_profile()

        for profile in profiles:
            if profile["name"].lower() == name.lower():
                profile_id = profile["id"]
                assert isinstance(profile_id, int)
                return profile_id

        raise ValueError(f"no quality profile with the name {name}")

    def _get_tag_for_user_id(self, user_id: int) -> int:
        tags = self._radarr.get_tag()
        assert isinstance(tags, list)

        for tag in tags:
            if str(user_id) in tag["label"]:
                tag_id = tag["id"]
                assert isinstance(tag_id, int)
                return tag_id

        raise ValueError(f"no tag with the user id {user_id}")


if __name__ == "__main__":
    from wi1_bot.config import config

    radarr = Radarr(str(config.radarr.url), config.radarr.api_key)
