from datetime import datetime, timezone

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TranscodeItem(Base):
    __tablename__ = "transcode_queue"
    # AUTOINCREMENT so job ids never get reused once the queue empties
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str]
    quality_profile: Mapped[str]
    original_language: Mapped[str | None]
    # leasing state: the webhook dispatches jobs to workers over HTTP; a claimed
    # job is leased so a crashed worker's job is reclaimed once the lease expires
    status: Mapped[str] = mapped_column(default="queued")  # queued | in_progress
    worker_id: Mapped[str | None] = mapped_column(default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(default=None)
    attempts: Mapped[int] = mapped_column(default=0)
    status_changed_at: Mapped[datetime] = mapped_column(default=_utcnow)

    def __repr__(self) -> str:
        return (
            f"TranscodeItem(id={self.id}, path={self.path!r}, "
            f"quality_profile={self.quality_profile!r}, "
            f"original_language={self.original_language!r}, "
            f"status={self.status!r}, worker_id={self.worker_id!r}, attempts={self.attempts}, "
            f"status_changed_at={self.status_changed_at!r})"
        )
