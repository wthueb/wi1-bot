from unittest.mock import MagicMock

import pytest

from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr
from wi1_bot.bot.leaderboard import get_leaderboard, refresh_leaderboard

ALICE = 111111111111111111
BOB = 222222222222222222


@pytest.fixture
def radarr() -> Radarr:
    return Radarr("http://localhost:7878", "k")


@pytest.fixture
def sonarr() -> Sonarr:
    return Sonarr("http://localhost:8989", "k")


def _radarr_tags(radarr: Radarr, details: list[dict]) -> None:
    radarr._radarr.tag.get_detail = MagicMock(return_value=details)


def _sonarr_library(sonarr: Sonarr, tags: list[dict], series: list[dict]) -> None:
    sonarr._sonarr.tag.get = MagicMock(return_value=tags)
    sonarr._sonarr.series.get = MagicMock(return_value=series)


def test_refresh_then_read(bot_db: None, radarr: Radarr, sonarr: Sonarr) -> None:
    _radarr_tags(
        radarr,
        [
            {"id": 10, "label": f"alice-{ALICE}", "movieIds": [1, 2, 3]},
            {"id": 20, "label": f"bob-{BOB}", "movieIds": [4]},
            {"id": 30, "label": "random-non-user-tag", "movieIds": [9]},
        ],
    )
    _sonarr_library(
        sonarr, [{"id": 10, "label": f"alice-{ALICE}"}], [{"tags": [10]}, {"tags": [10]}]
    )

    refresh_leaderboard(radarr, sonarr)
    rows, updated_at = get_leaderboard()

    assert updated_at is not None
    assert [(r.discord_id, r.movie_count, r.series_count, r.total) for r in rows] == [
        (ALICE, 3, 2, 5),
        (BOB, 1, 0, 1),
    ]


def test_empty_cache(bot_db: None, radarr: Radarr, sonarr: Sonarr) -> None:
    _radarr_tags(radarr, [])
    _sonarr_library(sonarr, [], [])

    refresh_leaderboard(radarr, sonarr)
    rows, updated_at = get_leaderboard()

    assert rows == []
    assert updated_at is None


def test_refresh_drops_stale_users(bot_db: None, radarr: Radarr, sonarr: Sonarr) -> None:
    _sonarr_library(sonarr, [], [])
    _radarr_tags(radarr, [{"id": 10, "label": f"alice-{ALICE}", "movieIds": [1, 2]}])
    refresh_leaderboard(radarr, sonarr)

    _radarr_tags(radarr, [{"id": 20, "label": f"bob-{BOB}", "movieIds": [1]}])
    refresh_leaderboard(radarr, sonarr)

    rows, _ = get_leaderboard()
    assert [r.discord_id for r in rows] == [BOB]


def test_zero_count_users_excluded(bot_db: None, radarr: Radarr, sonarr: Sonarr) -> None:
    _radarr_tags(radarr, [{"id": 10, "label": f"alice-{ALICE}", "movieIds": []}])
    _sonarr_library(sonarr, [{"id": 10, "label": f"alice-{ALICE}"}], [])

    refresh_leaderboard(radarr, sonarr)
    rows, _ = get_leaderboard()

    assert rows == []

    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from wi1_bot.bot.db import get_engine
    from wi1_bot.bot.models import LeaderboardEntry

    with Session(get_engine()) as session:
        assert session.execute(select(func.count()).select_from(LeaderboardEntry)).scalar() == 0
