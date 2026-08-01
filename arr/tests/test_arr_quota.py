from unittest.mock import MagicMock, patch

import pytest

from wi1_bot.arr.common import user_id_from_tag
from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr

ALICE_ID = 111111111111111
BOB_ID = 222111111111111111
ALICE_LABEL = f"alice-{ALICE_ID}"
BOB_LABEL = f"bob-{BOB_ID}"
ALICE_TAG = {"id": 10, "label": ALICE_LABEL}
BOB_TAG = {"id": 20, "label": BOB_LABEL}


class TestUserIdFromTag:
    def test_current_format(self) -> None:
        assert user_id_from_tag("william-123456789012345678") == 123456789012345678

    def test_legacy_format(self) -> None:
        assert user_id_from_tag("william: 123456789012345678") == 123456789012345678

    def test_non_user_tag(self) -> None:
        assert user_id_from_tag("sonarr-favorites") is None

    def test_short_number_is_not_a_user(self) -> None:
        assert user_id_from_tag("season-2") is None

    def test_only_matches_the_trailing_id(self) -> None:
        assert user_id_from_tag(BOB_LABEL) == BOB_ID
        assert user_id_from_tag(BOB_LABEL) != ALICE_ID


class TestRadarrQuota:
    @pytest.fixture
    def radarr(self) -> Radarr:
        with patch("wi1_bot.arr.radarr.RadarrClient"):
            return Radarr("http://localhost:7878", "fake-api-key")

    def test_attributes_by_trailing_id_not_substring(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get = MagicMock(return_value=[ALICE_TAG, BOB_TAG])
        radarr._radarr.movie.get = MagicMock(
            return_value=[
                {"tags": [10], "sizeOnDisk": 100},  # alice
                {"tags": [20], "sizeOnDisk": 500},  # bob
            ]
        )

        amounts = radarr.get_quota_amounts([ALICE_ID, BOB_ID])

        assert amounts == {ALICE_ID: 100, BOB_ID: 500}

    def test_untagged_user_is_zero(self, radarr: Radarr) -> None:
        radarr._radarr.tag.get = MagicMock(return_value=[ALICE_TAG])
        radarr._radarr.movie.get = MagicMock(return_value=[{"tags": [10], "sizeOnDisk": 100}])

        assert radarr.get_quota_amounts([999999999999999999]) == {999999999999999999: 0}


class TestSonarrQuota:
    @pytest.fixture
    def sonarr(self) -> Sonarr:
        with patch("wi1_bot.arr.sonarr.SonarrClient"):
            return Sonarr("http://localhost:8989", "fake-api-key")

    def test_attributes_by_trailing_id_not_substring(self, sonarr: Sonarr) -> None:
        sonarr._sonarr.tag.get = MagicMock(return_value=[ALICE_TAG, BOB_TAG])
        sonarr._sonarr.series.get = MagicMock(
            return_value=[
                {"tags": [10], "statistics": {"sizeOnDisk": 100}},  # alice
                {"tags": [20], "statistics": {"sizeOnDisk": 500}},  # bob
            ]
        )

        amounts = sonarr.get_quota_amounts([ALICE_ID, BOB_ID])

        assert amounts == {ALICE_ID: 100, BOB_ID: 500}
