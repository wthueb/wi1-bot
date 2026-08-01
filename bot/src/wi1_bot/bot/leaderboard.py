from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.bot.db import get_engine
from wi1_bot.bot.models import LeaderboardEntry, utcnow

from .discord.helpers import parse_user_tag


def _counts_by_user(counts_by_label: dict[str, int]) -> dict[int, int]:
    result: dict[int, int] = {}
    for label, count in counts_by_label.items():
        if (parsed := parse_user_tag(label)) is not None:
            result[parsed[1]] = result.get(parsed[1], 0) + count
    return result


def refresh_leaderboard(radarr: Radarr, sonarr: Sonarr) -> None:
    movie_counts = _counts_by_user(radarr.get_tag_title_counts())
    series_counts = _counts_by_user(sonarr.get_tag_title_counts())

    now = utcnow()

    with Session(get_engine()) as session:
        session.execute(delete(LeaderboardEntry))
        session.add_all(
            LeaderboardEntry(
                discord_id=uid,
                movie_count=movie_counts.get(uid, 0),
                series_count=series_counts.get(uid, 0),
                updated_at=now,
            )
            for uid in movie_counts.keys() | series_counts.keys()
            # a tag can exist with no titles; don't cache rows that read-time would drop
            if movie_counts.get(uid, 0) + series_counts.get(uid, 0) > 0
        )
        session.commit()


@dataclass
class LeaderboardRow:
    discord_id: int
    movie_count: int
    series_count: int

    @property
    def total(self) -> int:
        return self.movie_count + self.series_count


def get_leaderboard() -> tuple[list[LeaderboardRow], datetime | None]:
    with Session(get_engine()) as session:
        entries = list(session.execute(select(LeaderboardEntry)).scalars().all())

    updated_at = max((e.updated_at for e in entries), default=None)

    rows = [
        LeaderboardRow(e.discord_id, e.movie_count, e.series_count)
        for e in entries
        if e.movie_count + e.series_count > 0
    ]
    rows.sort(key=lambda r: (-r.total, r.discord_id))

    return rows, updated_at
