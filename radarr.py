import logging
from shutil import rmtree

from pyarr import RadarrAPI

from config import RADARR_URL, RADARR_API_KEY
from movie import Movie


class RadarrAPI(RadarrAPI):
    def get_tag(self, id: int = None):
        if id is None:
            path = '/api/v3/tag'
        else:
            path = f'/api/v3/tag/{id}'

        res = self.request_get(path)

        return res

    def get_tag_detail(self, id: int = None):
        if id is None:
            path = '/api/v3/tag/detail'
        else:
            path = f'/api/v3/tag/detail/{id}'

        res = self.request_get(path)

        return res

    def create_tag(self, label: str):
        path = '/api/v3/tag'

        tag_json = {'id': 0, 'label': label}

        res = self.request_post(path, data=tag_json)

        return res

    def add_tag(self, movie_id: int, tag_id: int):
        path = '/api/v3/movie/editor'

        edit_json = {'movieIds': [movie_id], 'tags': [tag_id], 'applyTags': 'add'}

        res = self.request_put(path, data=edit_json)

        return res


class Radarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._logger = logging.getLogger(__name__)

        self._logger.debug('authenticating with radarr')

        self._radarr = RadarrAPI(url, api_key)

    def lookup_movie(self, query: str) -> list:
        possible_movies = self._radarr.lookup_movie(query)

        return [Movie(m) for m in possible_movies]

    def lookup_library(self, query: str) -> list:
        movies = self._radarr.get_movie()

        keywords = query.split()

        matching = []

        for m in movies:
            match = True

            movie = Movie(m)

            for keyword in keywords:
                if keyword.lower() not in movie.full_title.lower():
                    match = False
                    break

            if match:
                matching.append(movie)

        return matching

    def add_movie(self, movie: Movie, profile: str = 'good') -> bool:
        if self._radarr.get_movie(movie.tmdb_id):
            return False

        quality_profile_id = self._get_quality_profile(profile)

        if quality_profile_id is None:
            raise ValueError(f'{profile} is not a valid quality profile name')

        root_folder = self._radarr.get_root_folder()[0]['path']

        self._radarr.add_movie(db_id=movie.tmdb_id,
                               quality_profile_id=quality_profile_id, root_dir=root_folder)

        return True

    def add_tag(self, movie: Movie, user_id: int) -> bool:
        movie_json = self._radarr.get_movie(movie.tmdb_id)[0]

        tag_id = self._get_tag_for_user(user_id)

        if tag_id is None:
            # tag_id = self._radarr.create_tag(str(user_id))['id']

            self._logger.warning('user does not have a tag')

            return False

        self._radarr.add_tag(movie_json['id'], tag_id)

        return True

    def del_movie(self, movie: Movie) -> None:
        movie_json = self._radarr.get_movie(movie.tmdb_id)[0]

        db_id = movie_json['id']
        path = movie_json['folderName']

        self._radarr.del_movie(db_id, del_files=True, add_exclusion=False)

        try:
            rmtree(path)
        except FileNotFoundError:
            pass

    def search_missing(self) -> None:
        return self._radarr.post_command(name='MissingMoviesSearch')

    def get_quota_amount(self, user_id: int) -> int:
        tag_id = self._get_tag_for_user(user_id)

        if tag_id is None:
            return 0

        tag_details = self._radarr.get_tag_detail(tag_id)

        tagged_movies = tag_details['movieIds']

        total = 0

        for movie in self._radarr.get_movie():
            if movie['id'] in tagged_movies:
                total += movie['sizeOnDisk']

        return total

    def _get_quality_profile(self, label: str):
        profiles = self._radarr.get_quality_profiles()

        for profile in profiles:
            if profile['name'].lower() == label.lower():
                return profile['id']

        return None

    def _get_tag_for_user(self, user_id: int):
        tags = self._radarr.get_tag()

        for tag in tags:
            if str(user_id) in tag['label']:
                return tag['id']

        return None


if __name__ == '__main__':
    radarr_api = RadarrAPI(RADARR_URL, RADARR_API_KEY)
    radarr = Radarr(RADARR_URL, RADARR_API_KEY)
