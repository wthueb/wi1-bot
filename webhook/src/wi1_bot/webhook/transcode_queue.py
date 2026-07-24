import threading
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_engine
from wi1_bot.webhook.metrics import (
    JOB_ATTEMPT_DURATION,
    JOB_ATTEMPTS,
    JOB_CLAIMS,
    JOB_HEARTBEATS,
    JOB_QUEUE_WAIT_DURATION,
    elapsed_seconds,
)
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

            previous_status = item.status
            previous_status_changed_at = item.status_changed_at
            if previous_status == "queued":
                claim_kind = "initial" if item.attempts == 0 else "retry"
            else:
                claim_kind = "expired_lease"

            item.status = "in_progress"
            item.worker_id = worker_id
            item.lease_expires_at = now + timedelta(seconds=lease_secs)
            item.attempts += 1
            item.status_changed_at = now
            session.commit()
            session.refresh(item)
            session.expunge(item)

            JOB_CLAIMS.labels(kind=claim_kind).inc()
            if claim_kind in {"initial", "retry"}:
                JOB_QUEUE_WAIT_DURATION.labels(kind=claim_kind).observe(
                    elapsed_seconds(previous_status_changed_at, now)
                )
            else:
                JOB_ATTEMPTS.labels(outcome="lease_expired").inc()
                JOB_ATTEMPT_DURATION.labels(outcome="lease_expired").observe(
                    elapsed_seconds(previous_status_changed_at, now)
                )
            return item

    def heartbeat(self, item_id: int, worker_id: str, lease_secs: float | None = None) -> bool:
        """Extend a claimed job's lease. Only the owning worker may renew it."""
        if lease_secs is None:
            lease_secs = config.webhook.lease_secs
        with Session(get_engine()) as session:
            item = session.get(TranscodeItem, item_id)
            if item is None or item.status != "in_progress" or item.worker_id != worker_id:
                JOB_HEARTBEATS.labels(outcome="rejected").inc()
                return False
            item.lease_expires_at = _utcnow() + timedelta(seconds=lease_secs)
            session.commit()
            JOB_HEARTBEATS.labels(outcome="accepted").inc()
            return True

    def complete(
        self, item_id: int, outcome: Literal["completed", "skipped"] = "completed"
    ) -> str | None:
        """Remove a finished job; returns its path (for a post-transcode rescan)."""
        with Session(get_engine()) as session:
            item = session.get(TranscodeItem, item_id)
            if item is None:
                return None
            path = item.path
            attempt_started_at = item.status_changed_at if item.status == "in_progress" else None
            session.delete(item)
            session.commit()

            if attempt_started_at is not None:
                JOB_ATTEMPTS.labels(outcome=outcome).inc()
                JOB_ATTEMPT_DURATION.labels(outcome=outcome).observe(
                    elapsed_seconds(attempt_started_at, _utcnow())
                )
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
            attempt_started_at = item.status_changed_at if item.status == "in_progress" else None
            if retry and item.attempts < max_attempts:
                now = _utcnow()
                item.status = "queued"
                item.worker_id = None
                item.lease_expires_at = None
                item.status_changed_at = now
                session.commit()

                if attempt_started_at is not None:
                    JOB_ATTEMPTS.labels(outcome="requeued").inc()
                    JOB_ATTEMPT_DURATION.labels(outcome="requeued").observe(
                        elapsed_seconds(attempt_started_at, now)
                    )
                return None
            session.delete(item)
            session.commit()

            if attempt_started_at is not None:
                JOB_ATTEMPTS.labels(outcome="terminal_failure").inc()
                JOB_ATTEMPT_DURATION.labels(outcome="terminal_failure").observe(
                    elapsed_seconds(attempt_started_at, _utcnow())
                )
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
