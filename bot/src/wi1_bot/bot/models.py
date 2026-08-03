import enum
from datetime import datetime, timezone

from sqlalchemy import Enum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class RequestKind(enum.StrEnum):
    MOVIE = "movie"
    SERIES = "series"


class Request(Base):
    __tablename__ = "requests"
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    discord_id: Mapped[int]
    kind: Mapped[RequestKind] = mapped_column(
        Enum(RequestKind, values_callable=lambda enum_type: [kind.value for kind in enum_type])
    )
    tmdb_id: Mapped[int | None] = mapped_column(default=None)
    tvdb_id: Mapped[int | None] = mapped_column(default=None)
    title: Mapped[str]
    channel_id: Mapped[int]
    requested_at: Mapped[datetime] = mapped_column(default=utcnow)
    notified_at: Mapped[datetime | None] = mapped_column(default=None)

    def __repr__(self) -> str:
        return (
            f"Request(id={self.id}, discord_id={self.discord_id}, kind={self.kind!r}, "
            f"tmdb_id={self.tmdb_id}, tvdb_id={self.tvdb_id}, title={self.title!r}, "
            f"notified_at={self.notified_at!r})"
        )


class SeenEpisode(Base):
    __tablename__ = "seen_episodes"

    tvdb_id: Mapped[int] = mapped_column(primary_key=True)
    episode_id: Mapped[int] = mapped_column(primary_key=True)
    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow)

    def __repr__(self) -> str:
        return f"SeenEpisode(tvdb_id={self.tvdb_id}, episode_id={self.episode_id})"


class NotifyMethod(enum.StrEnum):
    DM = "dm"
    CHANNEL = "channel"


class UserSettings(Base):
    __tablename__ = "user_settings"

    discord_id: Mapped[int] = mapped_column(primary_key=True)
    notify_method: Mapped[NotifyMethod] = mapped_column(
        Enum(NotifyMethod, values_callable=lambda enum_type: [kind.value for kind in enum_type]),
        default=NotifyMethod.CHANNEL,
    )
    auto_select_single: Mapped[bool] = mapped_column(default=True)
    auto_notify: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    def __repr__(self) -> str:
        return f"UserSettings(discord_id={self.discord_id}, notify_method={self.notify_method!r})"


class LeaderboardEntry(Base):
    __tablename__ = "leaderboard"

    discord_id: Mapped[int] = mapped_column(primary_key=True)
    movie_count: Mapped[int] = mapped_column(default=0)
    series_count: Mapped[int] = mapped_column(default=0)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow)

    def __repr__(self) -> str:
        return (
            f"LeaderboardEntry(discord_id={self.discord_id}, movie_count={self.movie_count}, "
            f"series_count={self.series_count})"
        )
