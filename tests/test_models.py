from wi1_bot.arr.download import Download
from wi1_bot.arr.episode import Episode
from wi1_bot.arr.movie import Movie


class TestMovie:
    def test_movie_creation_with_imdb(self) -> None:
        movie_json = {
            "title": "The Matrix",
            "year": 1999,
            "tmdbId": 603,
            "imdbId": "tt0133093",
        }
        movie = Movie(movie_json)

        assert movie.title == "The Matrix"
        assert movie.year == 1999
        assert movie.tmdb_id == 603
        assert movie.imdb_id == "tt0133093"
        assert movie.full_title == "The Matrix (1999)"
        assert movie.url == "https://imdb.com/title/tt0133093"

    def test_movie_creation_without_imdb(self) -> None:
        movie_json = {
            "title": "Inception",
            "year": 2010,
            "tmdbId": 27205,
        }
        movie = Movie(movie_json)

        assert movie.title == "Inception"
        assert movie.year == 2010
        assert movie.tmdb_id == 27205
        assert movie.imdb_id == ""
        assert movie.full_title == "Inception (2010)"
        assert movie.url == "https://themoviedb.org/movie/27205"

    def test_movie_str_representation(self) -> None:
        movie_json = {
            "title": "The Matrix",
            "year": 1999,
            "tmdbId": 603,
            "imdbId": "tt0133093",
        }
        movie = Movie(movie_json)

        assert str(movie) == "[The Matrix (1999)](https://imdb.com/title/tt0133093)"


class TestEpisode:
    def test_episode_creation_with_imdb(self) -> None:
        episode_json = {
            "title": "Winter Is Coming",
            "seasonNumber": 1,
            "episodeNumber": 1,
            "airDate": "2011-04-17",
        }
        episode = Episode(
            episode_json,
            series_title="Game of Thrones",
            series_tvdb_id=121361,
            series_imdb_id="tt0944947",
        )

        assert episode.ep_title == "Winter Is Coming"
        assert episode.season_num == 1
        assert episode.ep_num == 1
        assert episode.series_title == "Game of Thrones"
        assert episode.air_date == "2011-04-17"
        assert episode.full_title == "Game of Thrones S01E01 - Winter Is Coming"
        assert episode.url == "https://www.imdb.com/title/tt0944947"

    def test_episode_creation_without_imdb(self) -> None:
        episode_json = {
            "title": "Pilot",
            "seasonNumber": 1,
            "episodeNumber": 1,
            "airDate": "2008-01-20",
        }
        episode = Episode(
            episode_json,
            series_title="Breaking Bad",
            series_tvdb_id=81189,
            series_imdb_id="",
        )

        assert episode.ep_title == "Pilot"
        assert episode.season_num == 1
        assert episode.ep_num == 1
        assert episode.full_title == "Breaking Bad S01E01 - Pilot"
        assert episode.url == "https://www.thetvdb.com/?id=81189"

    def test_episode_str_representation(self) -> None:
        episode_json = {
            "title": "Winter Is Coming",
            "seasonNumber": 1,
            "episodeNumber": 1,
            "airDate": "2011-04-17",
        }
        episode = Episode(
            episode_json,
            series_title="Game of Thrones",
            series_tvdb_id=121361,
            series_imdb_id="tt0944947",
        )

        assert (
            str(episode)
            == "[Game of Thrones S01E01 - Winter Is Coming](https://www.imdb.com/title/tt0944947)"
        )


class TestDownload:
    def test_download_with_movie(self) -> None:
        data = {
            "movie": {
                "title": "The Matrix",
                "year": 1999,
                "tmdbId": 603,
                "imdbId": "tt0133093",
            },
            "sizeleft": 500_000_000,
            "size": 1_000_000_000,
            "timeleft": "00:15:30",
            "status": "downloading",
        }
        download = Download(data)

        assert isinstance(download.content, Movie)
        assert download.content.title == "The Matrix"
        assert download.sizeleft == 500_000_000
        assert download.size == 1_000_000_000
        assert download.timeleft == "00:15:30"
        assert download.status == "downloading"
        assert download.pct_done == 50.0

    def test_download_with_episode(self) -> None:
        data = {
            "episode": {
                "title": "Winter Is Coming",
                "seasonNumber": 1,
                "episodeNumber": 1,
                "airDate": "2011-04-17",
            },
            "series": {
                "title": "Game of Thrones",
                "tvdbId": 121361,
                "imdbId": "tt0944947",
            },
            "sizeleft": 250_000_000,
            "size": 1_000_000_000,
            "timeleft": "00:10:00",
            "status": "downloading",
        }
        download = Download(data)

        assert isinstance(download.content, Episode)
        assert download.content.series_title == "Game of Thrones"
        assert download.pct_done == 75.0

    def test_download_with_unknown_content(self) -> None:
        data = {
            "title": "Unknown Release",
            "sizeleft": 100_000_000,
            "size": 1_000_000_000,
            "status": "downloading",
        }
        download = Download(data)

        assert download.content == "Unknown Release"
        assert download.timeleft == "unknown"
        assert download.pct_done == 90.0

    def test_download_str_representation(self) -> None:
        data = {
            "movie": {
                "title": "The Matrix",
                "year": 1999,
                "tmdbId": 603,
                "imdbId": "tt0133093",
            },
            "sizeleft": 500_000_000,
            "size": 1_000_000_000,
            "timeleft": "00:15:30",
            "status": "downloading",
        }
        download = Download(data)

        result = str(download)
        assert "The Matrix (1999)" in result
        assert "50.0% done" in result
        assert "00:15:30" in result
