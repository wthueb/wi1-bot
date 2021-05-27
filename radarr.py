import logging
from shutil import rmtree

from pyarr import RadarrAPIv3

from movie import Movie


class Radarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._logger = logging.getLogger(__name__)

        self._logger.debug('authenticating with radarr')

        self._radarr = RadarrAPIv3(url, api_key)

        quality_profiles = self._radarr.get_quality_profiles()

        self._logger.debug(f'available quality profiles: {quality_profiles}')

        self._good_profile_id = None

        for prof in quality_profiles:
            if prof['name'] == 'good':
                self._good_profile_id = prof['id']

        if not self._good_profile_id:
            self._logger.error('cannot find id of "good" profile, exiting')

            raise Exception('cannot find id of "good" profile, exiting')

        self._logger.debug(f'"good" profile id: {self._good_profile_id}')

    def lookup_movie(self, query: str) -> list:
        possible_movies = self._radarr.lookup_movie(query)

        return [Movie(m) for m in possible_movies]

    def lookup_library(self, query: str) -> list:
        movies = self._radarr.get_movie()

        keywords = query.split()

        return [Movie(m) for m in movies for k in keywords if k.lower() in m.full_title.lower()]

    def add_movie(self, movie: Movie) -> bool:
        if self._radarr.get_movie(movie.tmdb_id):
            return False

        self._radarr.add_movie(dbId=movie.tmdb_id, qualityProfileId=self._good_profile_id)

        return True

    def del_movie(self, movie: Movie) -> None:
        movie_json = self._radarr.get_movie(movie.tmdb_id)[0]

        radarrId = movie_json['id']
        path = movie_json['folderName']

        self._radarr.del_movie(radarrId, delFiles=True, addExclusion=False)

        try:
            rmtree(path)
        except FileNotFoundError:
            pass

    def search_missing(self) -> None:
        return self._radarr.post_command(name='MissingMoviesSearch')
