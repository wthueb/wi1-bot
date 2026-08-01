from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr

ALICE_TAG = "alice-111111111111111111"
BOB_TAG = "bob-222222222222222222"
EMPTY_TAG = "carol-333333333333333333"


class TestRadarrTitleCounts:
    @pytest.fixture
    def radarr(self) -> Radarr:
        with patch("wi1_bot.arr.radarr.RadarrClient"):
            return Radarr("http://localhost:7878", "fake-api-key")

    def test_counts_from_tag_details(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get_detail = MagicMock(
            return_value=[
                {"id": 10, "label": ALICE_TAG, "movieIds": [1, 2]},
                {"id": 20, "label": BOB_TAG, "movieIds": [2, 3]},
                {"id": 30, "label": EMPTY_TAG, "movieIds": []},
            ]
        )

        assert radarr.get_tag_title_counts() == {ALICE_TAG: 2, BOB_TAG: 2, EMPTY_TAG: 0}

    def test_no_tags(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get_detail = MagicMock(return_value=[])

        assert radarr.get_tag_title_counts() == {}

    def test_never_scans_the_library(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get_detail = MagicMock(
            return_value=[{"id": 10, "label": ALICE_TAG, "movieIds": [1]}]
        )
        radarr._radarr.movie.get = MagicMock()

        radarr.get_tag_title_counts()

        radarr._radarr.movie.get.assert_not_called()


class TestSonarrTitleCounts:
    @pytest.fixture
    def sonarr(self) -> Sonarr:
        with patch("wi1_bot.arr.sonarr.SonarrClient"):
            return Sonarr("http://localhost:8989", "fake-api-key")

    def test_counts_from_series_scan(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.tag.get = MagicMock(
            return_value=[
                {"id": 10, "label": ALICE_TAG},
                {"id": 20, "label": BOB_TAG},
                {"id": 30, "label": EMPTY_TAG},
            ]
        )
        sonarr._sonarr.series.get = MagicMock(
            return_value=[
                {"tags": [10]},  # alice
                {"tags": [10, 20]},  # alice + bob, shared series counts for both
                {"tags": []},  # untagged
            ]
        )

        assert sonarr.get_tag_title_counts() == {ALICE_TAG: 2, BOB_TAG: 1, EMPTY_TAG: 0}

    def test_no_tags_skips_series_scan(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.tag.get = MagicMock(return_value=[])
        sonarr._sonarr.series.get = MagicMock()

        assert sonarr.get_tag_title_counts() == {}
        sonarr._sonarr.series.get.assert_not_called()

    def test_ignores_download_state(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.tag.get = MagicMock(return_value=[{"id": 10, "label": ALICE_TAG}])
        sonarr._sonarr.series.get = MagicMock(return_value=[{"tags": [10]}])

        assert sonarr.get_tag_title_counts() == {ALICE_TAG: 1}
