import threading
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_engine
from wi1_bot.webhook.models import TranscodeItem

__all__ = ["TranscodeItem", "TranscodeQueue", "queue"]

MAX_ATTEMPTS = 3


def _utcnow() -> datetime:
    # store naive UTC so comparisons stay consistent across SQLite (which drops tzinfo)
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TranscodeQueue:
    """The webhook-owned transcode queue.

    Workers pull jobs over HTTP via :meth:`claim` and report the outcome via
    :meth:`complete` / :meth:`fail`. The webhook runs as a single process (waitress
    with a thread pool), so a process-level lock serializes claims — that plus the
    lease is enough to keep replicated workers from double-processing a job.
    """

    def __init__(self) -> None:
        self._claim_lock = threading.Lock()

    def add(
        self,
        path: str,
        quality_profile: str,
        original_language: str | None = None,
    ) -> int:
        """Enqueue a job; returns the new job's id (for log correlation)."""
        with Session(get_engine()) as session:
            item = TranscodeItem(
                path=path,
                quality_profile=quality_profile,
                original_language=original_language,
            )
            session.add(item)
            session.commit()
            return item.id

    def claim(self, worker_id: str, lease_secs: float | None = None) -> TranscodeItem | None:
        """Atomically hand the oldest available job to a worker.

        Picks the oldest ``queued`` row, or an ``in_progress`` row whose lease has
        expired (crashed worker), marks it in_progress with a fresh lease, bumps the
        attempt counter, and returns a detached copy.
        """
        if lease_secs is None:
            lease_secs = config.webhook.lease_secs
        now = _utcnow()
        with self._claim_lock, Session(get_engine()) as session:
            item = session.execute(
                select(TranscodeItem)
                .where(
                    (TranscodeItem.status == "queued")
                    | (
                        (TranscodeItem.status == "in_progress")
                        & (TranscodeItem.lease_expires_at < now)
                    )
                )
                .order_by(TranscodeItem.id)
                .limit(1)
            ).scalar_one_or_none()

            if item is None:
                return None

            item.status = "in_progress"
            item.worker_id = worker_id
            item.lease_expires_at = now + timedelta(seconds=lease_secs)
            item.attempts += 1
            session.commit()
            session.refresh(item)
            session.expunge(item)
            return item

    def heartbeat(self, item_id: int, worker_id: str, lease_secs: float | None = None) -> bool:
        """Extend a claimed job's lease. Only the owning worker may renew it."""
        if lease_secs is None:
            lease_secs = config.webhook.lease_secs
        with Session(get_engine()) as session:
            item = session.get(TranscodeItem, item_id)
            if item is None or item.status != "in_progress" or item.worker_id != worker_id:
                return False
            item.lease_expires_at = _utcnow() + timedelta(seconds=lease_secs)
            session.commit()
            return True

    def complete(self, item_id: int) -> str | None:
        """Remove a finished job; returns its path (for a post-transcode rescan)."""
        with Session(get_engine()) as session:
            item = session.get(TranscodeItem, item_id)
            if item is None:
                return None
            path = item.path
            session.delete(item)
            session.commit()
            return path

    def fail(self, item_id: int, retry: bool, max_attempts: int = MAX_ATTEMPTS) -> str | None:
        """Handle a failed job.

        Requeues it if ``retry`` and attempts remain (returns ``None``); otherwise
        drops it and returns its path so the caller can send a failure notification.
        """
        with Session(get_engine()) as session:
            item = session.get(TranscodeItem, item_id)
            if item is None:
                return None
            path = item.path
            if retry and item.attempts < max_attempts:
                item.status = "queued"
                item.worker_id = None
                item.lease_expires_at = None
                session.commit()
                return None
            session.delete(item)
            session.commit()
            return path

    def clear(self) -> None:
        with Session(get_engine()) as session:
            session.query(TranscodeItem).delete()
            session.commit()

    @property
    def size(self) -> int:
        with Session(get_engine()) as session:
            return session.query(TranscodeItem).count()


queue = TranscodeQueue()
