from shutil import rmtree

from pyarr import RadarrAPIv3


class Radarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._radarr = RadarrAPIv3(url, api_key)

        quality_profiles = self._radarr.get_quality_profiles()

        self._good_profile_id = None

        for prof in quality_profiles:
            if prof['name'] == 'good':
                self._good_profile_id = prof['id']

        if not self._good_profile_id:
            raise Exception('cannot find id of good profile, exiting')

    def lookup_movie(self, query: str) -> list:
        possible_movies = self._radarr.lookup_movie(query)

        return possible_movies

    def lookup_library(self, query) -> list:
        movies = self._radarr.get_movie()

        keywords = query.split()

        matching = []

        for movie in movies:
            good = True

            for keyword in keywords:
                if (keyword.lower() not in movie['title'].lower()
                        and keyword.lower() not in str(movie['year'])):
                    good = False
                    break

            if good:
                matching.append(movie)

        return matching

    def add_movie(self, tmdbId: int) -> bool:
        if self._radarr.get_movie(tmdbId):
            return False

        self._radarr.add_movie(dbId=tmdbId, qualityProfileId=self._good_profile_id)

        return True

    def del_movie(self, tmdbId: int) -> None:
        movie = self._radarr.get_movie(tmdbId)[0]

        radarrId = movie['id']
        path = movie['folderName']

        self._radarr.del_movie(radarrId, delFiles=True, addExclusion=False)

        try:
            rmtree(path)
        except FileNotFoundError:
            pass
