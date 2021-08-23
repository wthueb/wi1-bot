import logging
from shutil import rmtree

from pyarr import RadarrAPI


class Movie:
    def __init__(self, movie_json: dict) -> None:
        self.title = movie_json['title']
        self.year = movie_json['year']
        self.tmdb_id = movie_json['tmdbId']

        self.full_title = f'{self.title} ({self.year})'

        self.url = f'https://themoviedb.org/movie/{self.tmdb_id}'

        self.imdb_id = None

        try:
            self.imdb_id = movie_json['imdbId']
            self.url = f'https://imdb.com/title/{self.imdb_id}'
        except KeyError:
            pass

    def __str__(self) -> str:
        return f'[{self.full_title}]({self.url})'

    def __repr__(self) -> str:
        return str(self.__dict__)


class Download:
    def __init__(self, data: dict) -> None:
        self.movie = Movie(data['movie'])
        self.sizeleft = data['sizeleft']
        self.size = data['size']
        self.timeleft = data['timeleft'] if 'timeleft' in data else 'unknown'
        self.status = data['status']

        self.pct_done = (self.size-self.sizeleft) / self.size * 100

    def __str__(self) -> str:
        return (
            f'{self.movie}: {self.pct_done:.1f}% done '
            f'({(self.size-self.sizeleft) / 1024**3:.2f}/{self.size / 1024**3:.2f} GB)\n'
            f'eta: {self.timeleft}')

    def __repr__(self) -> str:
        return str(self.__dict__)


class Radarr:
    def __init__(self, url: str, api_key: str) -> None:
        self._logger = logging.getLogger(__name__)

        self._logger.debug('authenticating with radarr')

        self._radarr = RadarrAPI(url, api_key)

        self._logger.debug('successfully authenticated with radarr')

    def lookup_movie(self, query: str) -> list[Movie]:
        possible_movies = self._radarr.lookup_movie(query)

        return [Movie(m) for m in possible_movies]

    def lookup_library(self, query: str) -> list[Movie]:
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

        try:
            tag_id = self._get_tag_for_user(user_id)
        except ValueError:
            # tag_id = self._radarr.create_tag(str(user_id))['id']

            self._logger.warning(f'{user_id} does not have a tag')

            return False

        self._add_tag(movie_json['id'], tag_id)

        return True

    def del_movie(self, movie: Movie) -> None:
        potential = self._radarr.get_movie(movie.tmdb_id)

        if not potential:
            raise ValueError(f'{movie} is not in the library')

        movie_json = potential[0]

        db_id = movie_json['id']
        path = movie_json['folderName']

        self._radarr.del_movie(db_id, del_files=True, add_exclusion=False)

        try:
            rmtree(path)
        except FileNotFoundError:
            pass

    def search_missing(self) -> None:
        self._radarr.post_command(name='MissingMoviesSearch')

    def get_quota_amount(self, user_id: int) -> int:
        try:
            tag_id = self._get_tag_for_user(user_id)
        except ValueError:
            return 0

        tag_details = self._radarr.get_tag_details(tag_id)

        tagged_movies = tag_details['movieIds']

        total = 0

        for movie in self._radarr.get_movie():
            if movie['id'] in tagged_movies:
                total += movie['sizeOnDisk']

        return total

    def get_downloads(self) -> list[Download]:
        queue = self._radarr.get_queue_details()

        return sorted((Download(d) for d in queue), key=lambda d: (d.timeleft, -d.pct_done))

    def _get_quality_profile(self, label: str) -> int:
        profiles = self._radarr.get_quality_profiles()

        for profile in profiles:
            if profile['name'].lower() == label.lower():
                return profile['id']

        raise ValueError(f'no quality profile with the name {label}')

    def _get_tag_for_user(self, user_id: int) -> int:
        tags = self._radarr.get_tag()

        for tag in tags:
            if str(user_id) in tag['label']:
                return tag['id']

        raise ValueError(f'no tag with the user id {user_id}')

    def _add_tag(self, movie_id: int, tag_id: int) -> dict:
        path = '/api/v3/movie/editor'

        edit_json = {'movieIds': [movie_id], 'tags': [tag_id], 'applyTags': 'add'}

        res = self._radarr.request_put(path, data=edit_json)

        return res


if __name__ == '__main__':
    import yaml

    with open('config.yaml', 'rb') as f:
        config = yaml.load(f, Loader=yaml.SafeLoader)

    radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])
    pyarr = radarr._radarr
