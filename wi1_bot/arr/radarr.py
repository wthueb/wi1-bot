from shutil import rmtree

from pyarr import RadarrAPI

from .download import Download
from .movie import Movie


class Radarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._radarr = RadarrAPI(url, api_key)

    def lookup_movie(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.lookup_movie(query)

        return [Movie(m) for m in possible_movies]

    def lookup_library(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.lookup_movie(query)

        possible_movies = [Movie(m) for m in possible_movies if "id" in m]

        return possible_movies

    def get_quality_profile_name(self, profile_id: int):
        profiles = self._radarr.get_quality_profile()

        for profile in profiles:
            if profile["id"] == profile_id:
                return profile["name"]

        raise ValueError(f"no quality profile with the id {profile_id}")

    def add_movie(self, movie: Movie, profile: str = "good") -> bool:
        if self._radarr.get_movie(movie.tmdb_id):
            return False

        quality_profile_id = self._get_quality_profile_id(profile)

        root_folder = self._radarr.get_root_folder()[0]["path"]

        self._radarr.add_movie(
            db_id=movie.tmdb_id,
            quality_profile_id=quality_profile_id,
            root_dir=root_folder,
        )

        return True

    def add_tag(self, movie: Movie | list[Movie], user_id: int) -> bool:
        if isinstance(movie, Movie):
            ids = [self._radarr.get_movie(movie.tmdb_id)[0]["id"]]
        else:
            ids = [self._radarr.get_movie(m.tmdb_id)[0]["id"] for m in movie]

        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            # tag_id = self._radarr.create_tag(str(user_id))['id']

            return False

        edit_json = {"movieIds": ids, "tags": [tag_id], "applyTags": "add"}

        self._radarr.upd_movies(edit_json)

        return True

    def del_movie(self, movie: Movie) -> None:
        potential = self._radarr.get_movie(movie.tmdb_id)

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
        potential = self._radarr.get_movie(movie.tmdb_id)

        if not potential:
            return False

        files = self._radarr.get_movie_files_by_movie_id(potential[0]["id"])

        if files:
            return True

        return False

    def search_missing(self) -> None:
        self._radarr.post_command(name="MissingMoviesSearch")

    def lookup_user_movies(self, query: str, user_id: int) -> list[Movie]:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return []

        tag_detail = self._radarr.get_tag_detail(tag_id)

        possible_movies = self._radarr.lookup_movie(query)

        user_movie_ids = tag_detail["movieIds"]

        return [
            Movie(m) for m in possible_movies if "id" in m and m["id"] in user_movie_ids
        ]

    def get_quota_amount(self, user_id: int) -> int:
        try:
            tag_id = self._get_tag_for_user_id(user_id)
        except ValueError:
            return 0

        tag_detail = self._radarr.get_tag_detail(tag_id)

        tagged_movies = tag_detail["movieIds"]

        total = 0

        for movie in self._radarr.get_movie():
            if movie["id"] in tagged_movies:
                total += movie["sizeOnDisk"]

        return total

    def get_downloads(self) -> list[Download]:
        queue = self._radarr.get_queue_details()

        downloads = [Download(d) for d in queue]

        return sorted(downloads, key=lambda d: (d.timeleft, -d.pct_done))

    def rescan_movie(self, movie_id: int) -> None:
        self._radarr.post_command("RescanMovie", movieIds=[movie_id])

    def _get_quality_profile_id(self, name: str) -> int:
        profiles = self._radarr.get_quality_profile()

        for profile in profiles:
            if profile["name"].lower() == name.lower():
                return profile["id"]

        raise ValueError(f"no quality profile with the name {name}")

    def _get_tag_for_user_id(self, user_id: int) -> int:
        tags = self._radarr.get_tag()

        for tag in tags:
            if str(user_id) in tag["label"]:
                return tag["id"]

        raise ValueError(f"no tag with the user id {user_id}")


if __name__ == "__main__":
    from wi1_bot.config import config

    radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
    pyarr = radarr._radarr
