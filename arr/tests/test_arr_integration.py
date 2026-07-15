from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.arr.movie import Movie
from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Series, Sonarr


class TestRadarr:
    @pytest.fixture
    def radarr(self) -> Radarr:
        with patch("wi1_bot.arr.radarr.RadarrClient"):
            return Radarr("http://localhost:7878", "fake-api-key")

    @pytest.fixture
    def sample_movie_json(self) -> dict[str, Any]:
        return {
            "title": "The Matrix",
            "year": 1999,
            "tmdbId": 603,
            "imdbId": "tt0133093",
        }

    def test_lookup_movie(self, radarr: Radarr, sample_movie_json: dict[str, Any]) -> None:
        radarr._radarr.movie.lookup = MagicMock(return_value=[sample_movie_json])

        movies = radarr.lookup_movie("The Matrix")

        assert len(movies) == 1
        assert movies[0].title == "The Matrix"
        assert movies[0].year == 1999
        radarr._radarr.movie.lookup.assert_called_once_with(term="The Matrix")

    def test_lookup_library_filters_by_id(
        self, radarr: Radarr, sample_movie_json: dict[str, Any]
    ) -> None:
        movie_with_id = {**sample_movie_json, "id": 1}
        movie_without_id = sample_movie_json.copy()

        radarr._radarr.movie.lookup = MagicMock(return_value=[movie_with_id, movie_without_id])

        movies = radarr.lookup_library("The Matrix")

        assert len(movies) == 1
        assert movies[0].title == "The Matrix"

    def test_lookup_user_library_no_tag(self, radarr: Radarr) -> None:
        radarr._get_tag_for_user_id = MagicMock(side_effect=ValueError)

        movies = radarr.lookup_user_library("The Matrix", 123456)

        assert movies == []

    def test_lookup_user_library_with_tag(
        self, radarr: Radarr, sample_movie_json: dict[str, Any]
    ) -> None:
        movie_with_user_tag = {**sample_movie_json, "id": 1}
        movie_without_user_tag = {**sample_movie_json, "id": 2}

        radarr._get_tag_for_user_id = MagicMock(return_value=5)
        radarr._radarr.tag.get_detail = MagicMock(return_value={"movieIds": [1]})
        radarr._radarr.movie.lookup = MagicMock(
            return_value=[movie_with_user_tag, movie_without_user_tag]
        )

        movies = radarr.lookup_user_library("The Matrix", 123456)

        assert len(movies) == 1
        assert movies[0].json["id"] == 1

    def test_add_movie_already_exists(
        self, radarr: Radarr, sample_movie_json: dict[str, Any]
    ) -> None:
        movie = Movie(sample_movie_json)
        radarr._radarr.movie.get = MagicMock(return_value=[{"id": 1}])

        result = radarr.add_movie(movie)

        assert result is False
        radarr._radarr.movie.add.assert_not_called()  # ty: ignore[unresolved-attribute]

    def test_add_movie_success(self, radarr: Radarr, sample_movie_json: dict[str, Any]) -> None:
        movie = Movie(sample_movie_json)
        radarr._radarr.movie.get = MagicMock(return_value=[])
        radarr._get_quality_profile_id = MagicMock(return_value=1)
        radarr._radarr.root_folder.get = MagicMock(return_value=[{"path": "/movies"}])
        radarr._radarr.movie.add = MagicMock()

        result = radarr.add_movie(movie)

        assert result is True
        radarr._radarr.movie.add.assert_called_once()

    def test_movie_downloaded_true(self, radarr: Radarr, sample_movie_json: dict[str, Any]) -> None:
        movie = Movie(sample_movie_json)
        radarr._radarr.movie.get = MagicMock(return_value=[{"id": 1}])
        radarr._radarr.movie_file.get = MagicMock(
            return_value=[{"id": 1, "path": "/path/to/movie.mkv"}]
        )

        result = radarr.movie_downloaded(movie)

        assert result is True

    def test_movie_downloaded_false(
        self, radarr: Radarr, sample_movie_json: dict[str, Any]
    ) -> None:
        movie = Movie(sample_movie_json)
        radarr._radarr.movie.get = MagicMock(return_value=[{"id": 1}])
        radarr._radarr.movie_file.get = MagicMock(return_value=[])

        result = radarr.movie_downloaded(movie)

        assert result is False

    def test_movie_not_in_library(self, radarr: Radarr, sample_movie_json: dict[str, Any]) -> None:
        movie = Movie(sample_movie_json)
        radarr._radarr.movie.get = MagicMock(return_value=[])

        result = radarr.movie_downloaded(movie)

        assert result is False

    def test_get_tag_for_user_id_exists(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get = MagicMock(
            return_value=[
                {"id": 1, "label": "user-123456"},
                {"id": 2, "label": "user-789012"},
            ]
        )

        tag_id = radarr._get_tag_for_user_id(123456)

        assert tag_id == 1

    def test_get_tag_for_user_id_not_exists(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get = MagicMock(return_value=[{"id": 1, "label": "user-789012"}])

        with pytest.raises(ValueError, match="no tag with the user id 123456"):
            radarr._get_tag_for_user_id(123456)

    def test_get_quality_profile_id_exists(self, radarr: Radarr) -> None:
        radarr._radarr.quality_profile.get = MagicMock(
            return_value=[
                {"id": 1, "name": "Good"},
                {"id": 2, "name": "HD-1080p"},
            ]
        )

        profile_id = radarr._get_quality_profile_id("good")

        assert profile_id == 1

    def test_get_quality_profile_id_not_exists(self, radarr: Radarr) -> None:
        radarr._radarr.quality_profile.get = MagicMock(return_value=[{"id": 1, "name": "HD-1080p"}])

        with pytest.raises(ValueError, match="no quality profile with the name bad"):
            radarr._get_quality_profile_id("bad")


class TestSonarr:
    @pytest.fixture
    def sonarr(self) -> Sonarr:
        with patch("wi1_bot.arr.sonarr.SonarrClient"):
            return Sonarr("http://localhost:8989", "fake-api-key")

    @pytest.fixture
    def sample_series_json(self) -> dict[str, Any]:
        return {
            "title": "Game of Thrones",
            "year": 2011,
            "tvdbId": 121361,
            "imdbId": "tt0944947",
        }

    def test_lookup_series(self, sonarr: Sonarr, sample_series_json: dict[str, Any]) -> None:
        sonarr._sonarr.series.lookup = MagicMock(return_value=[sample_series_json])

        series_list = sonarr.lookup_series("Game of Thrones")

        assert len(series_list) == 1
        assert series_list[0].title == "Game of Thrones"
        assert series_list[0].year == 2011
        sonarr._sonarr.series.lookup.assert_called_once_with(term="Game of Thrones")

    def test_lookup_library_filters_by_id(
        self, sonarr: Sonarr, sample_series_json: dict[str, Any]
    ) -> None:
        series_with_id = {**sample_series_json, "id": 1}
        series_without_id = sample_series_json.copy()

        sonarr._sonarr.series.lookup = MagicMock(return_value=[series_with_id, series_without_id])

        series_list = sonarr.lookup_library("Game of Thrones")

        assert len(series_list) == 1
        assert series_list[0].title == "Game of Thrones"

    def test_lookup_user_library_no_tag(self, sonarr: Sonarr) -> None:
        sonarr._get_tag_for_user_id = MagicMock(side_effect=ValueError)

        series_list = sonarr.lookup_user_library("Game of Thrones", 123456)

        assert series_list == []

    def test_lookup_user_library_with_tag(
        self, sonarr: Sonarr, sample_series_json: dict[str, Any]
    ) -> None:
        series_with_user_tag = {**sample_series_json, "tags": [5]}
        series_without_user_tag = {**sample_series_json, "tags": [3]}

        sonarr._get_tag_for_user_id = MagicMock(return_value=5)
        sonarr._sonarr.series.lookup = MagicMock(
            return_value=[series_with_user_tag, series_without_user_tag]
        )

        series_list = sonarr.lookup_user_library("Game of Thrones", 123456)

        assert len(series_list) == 1

    def test_add_series_already_exists(
        self, sonarr: Sonarr, sample_series_json: dict[str, Any]
    ) -> None:
        series_json_with_id = {**sample_series_json, "id": 1}
        series = Series(series_json_with_id)

        result = sonarr.add_series(series)

        assert result is False
        sonarr._sonarr.series.add.assert_not_called()  # ty: ignore[unresolved-attribute]

    def test_add_series_success(self, sonarr: Sonarr, sample_series_json: dict[str, Any]) -> None:
        series = Series(sample_series_json)
        sonarr._get_quality_profile_id = MagicMock(return_value=1)
        sonarr._sonarr.root_folder.get = MagicMock(return_value=[{"path": "/tv"}])
        sonarr._sonarr.series.add = MagicMock(return_value={"id": 123})

        result = sonarr.add_series(series)

        assert result is True
        assert series.db_id == 123
        sonarr._sonarr.series.add.assert_called_once()

    def test_series_downloaded_true(
        self, sonarr: Sonarr, sample_series_json: dict[str, Any]
    ) -> None:
        series_json_with_id = {**sample_series_json, "id": 1}
        series = Series(series_json_with_id)
        sonarr._sonarr.episode_file.get = MagicMock(
            return_value=[{"id": 1, "path": "/path/to/episode.mkv"}]
        )

        result = sonarr.series_downloaded(series)

        assert result is True

    def test_series_downloaded_false(
        self, sonarr: Sonarr, sample_series_json: dict[str, Any]
    ) -> None:
        series_json_with_id = {**sample_series_json, "id": 1}
        series = Series(series_json_with_id)
        sonarr._sonarr.episode_file.get = MagicMock(return_value=[])

        result = sonarr.series_downloaded(series)

        assert result is False

    def test_series_not_in_library(
        self, sonarr: Sonarr, sample_series_json: dict[str, Any]
    ) -> None:
        series = Series(sample_series_json)

        result = sonarr.series_downloaded(series)

        assert result is False

    def test_get_tag_for_user_id_exists(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.tag.get = MagicMock(
            return_value=[
                {"id": 1, "label": "user-123456"},
                {"id": 2, "label": "user-789012"},
            ]
        )

        tag_id = sonarr._get_tag_for_user_id(123456)

        assert tag_id == 1

    def test_get_tag_for_user_id_not_exists(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.tag.get = MagicMock(return_value=[{"id": 1, "label": "user-789012"}])

        with pytest.raises(ValueError, match="no tag with the user id 123456"):
            sonarr._get_tag_for_user_id(123456)
