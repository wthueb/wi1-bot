from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from wi1_bot.bot.db import get_engine
from wi1_bot.bot.models import Request, RequestKind, utcnow


def _title_match(kind: RequestKind, tmdb_id: int | None, tvdb_id: int | None):
    # a pending (not-yet-notified) request from a user for one specific title
    return (
        Request.kind == kind,
        Request.tmdb_id == tmdb_id,
        Request.tvdb_id == tvdb_id,
        Request.notified_at.is_(None),
    )


@dataclass
class PendingRequest:
    id: int
    discord_id: int
    kind: RequestKind
    tmdb_id: int | None
    tvdb_id: int | None
    title: str
    channel_id: int


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


def pending_requests() -> list[PendingRequest]:
    with Session(get_engine()) as session:
        rows = session.execute(select(Request).where(Request.notified_at.is_(None))).scalars()
        return [
            PendingRequest(
                id=r.id,
                discord_id=r.discord_id,
                kind=RequestKind(r.kind),
                tmdb_id=r.tmdb_id,
                tvdb_id=r.tvdb_id,
                title=r.title,
                channel_id=r.channel_id,
            )
            for r in rows
        ]


def mark_notified(request_ids: Iterable[int]) -> None:
    ids = list(request_ids)
    if not ids:
        return

    with Session(get_engine()) as session:
        session.execute(update(Request).where(Request.id.in_(ids)).values(notified_at=utcnow()))
        session.commit()
