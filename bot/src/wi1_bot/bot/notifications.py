from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from wi1_bot.bot.db import get_engine
from wi1_bot.bot.models import Request, RequestKind, SeenEpisode, utcnow


def _title_match(kind: RequestKind, tmdb_id: int | None, tvdb_id: int | None):
    # a movie request completes once notified, so only un-notified rows count as
    # active; a series request is a standing subscription that survives notification
    conditions = [
        Request.kind == kind,
        Request.tmdb_id == tmdb_id,
        Request.tvdb_id == tvdb_id,
    ]
    if kind == RequestKind.MOVIE:
        conditions.append(Request.notified_at.is_(None))
    return conditions


@dataclass
class ActiveRequest:
    id: int
    discord_id: int
    kind: RequestKind
    tmdb_id: int | None
    tvdb_id: int | None
    title: str
    channel_id: int
    notified: bool = False


def record_request(
    *,
    discord_id: int,
    kind: RequestKind,
    title: str,
    channel_id: int,
    tmdb_id: int | None = None,
    tvdb_id: int | None = None,
) -> None:
    with Session(get_engine()) as session:
        existing = session.execute(
            select(Request.id).where(
                Request.discord_id == discord_id, *_title_match(kind, tmdb_id, tvdb_id)
            )
        ).first()
        if existing is not None:
            return

        session.add(
            Request(
                discord_id=discord_id,
                kind=kind,
                tmdb_id=tmdb_id,
                tvdb_id=tvdb_id,
                title=title,
                channel_id=channel_id,
            )
        )
        session.commit()


def remove_request(
    *,
    discord_id: int,
    kind: RequestKind,
    tmdb_id: int | None = None,
    tvdb_id: int | None = None,
) -> int:
    with Session(get_engine()) as session:
        rows = session.execute(
            select(Request).where(
                Request.discord_id == discord_id, *_title_match(kind, tmdb_id, tvdb_id)
            )
        ).scalars()

        removed = 0
        for row in rows:
            session.delete(row)
            removed += 1

        session.commit()
        return removed


def _is_active():
    # a movie leaves the active set once its notification lands; a series subscription
    # stands until the user removes it
    return (Request.kind == RequestKind.SERIES) | Request.notified_at.is_(None)


def _to_active(row: Request) -> ActiveRequest:
    return ActiveRequest(
        id=row.id,
        discord_id=row.discord_id,
        kind=RequestKind(row.kind),
        tmdb_id=row.tmdb_id,
        tvdb_id=row.tvdb_id,
        title=row.title,
        channel_id=row.channel_id,
        notified=row.notified_at is not None,
    )


def active_requests() -> list[ActiveRequest]:
    with Session(get_engine()) as session:
        rows = session.execute(select(Request).where(_is_active())).scalars()
        return [_to_active(r) for r in rows]


def requests_for_user(discord_id: int) -> list[ActiveRequest]:
    with Session(get_engine()) as session:
        rows = session.execute(
            select(Request).where(Request.discord_id == discord_id, _is_active())
        ).scalars()
        # sort here rather than in SQL: sqlite orders TEXT case-sensitively, which reads
        # as an arbitrary shuffle in a user-facing list
        return sorted((_to_active(r) for r in rows), key=lambda r: r.title.lower())


def mark_notified(request_ids: Iterable[int]) -> None:
    ids = list(request_ids)
    if not ids:
        return

    with Session(get_engine()) as session:
        session.execute(update(Request).where(Request.id.in_(ids)).values(notified_at=utcnow()))
        session.commit()


def seen_episode_ids(tvdb_id: int) -> set[int]:
    with Session(get_engine()) as session:
        rows = session.execute(
            select(SeenEpisode.episode_id).where(SeenEpisode.tvdb_id == tvdb_id)
        ).scalars()
        return set(rows)


def mark_episodes_seen(tvdb_id: int, episode_ids: Iterable[int]) -> None:
    ids = set(episode_ids)
    if not ids:
        return

    with Session(get_engine()) as session:
        existing = set(
            session.execute(
                select(SeenEpisode.episode_id).where(
                    SeenEpisode.tvdb_id == tvdb_id, SeenEpisode.episode_id.in_(ids)
                )
            ).scalars()
        )
        for episode_id in ids - existing:
            session.add(SeenEpisode(tvdb_id=tvdb_id, episode_id=episode_id))
        session.commit()


def prune_seen_episodes(subscribed_tvdb_ids: Iterable[int]) -> None:
    # drop episode state for shows nobody follows anymore so the table stays bounded
    ids = set(subscribed_tvdb_ids)

    with Session(get_engine()) as session:
        session.execute(delete(SeenEpisode).where(SeenEpisode.tvdb_id.not_in(ids)))
        session.commit()
