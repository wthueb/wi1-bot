from datetime import datetime

from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TranscodeItem(Base):
    __tablename__ = "transcode_queue"

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

    def __repr__(self) -> str:
        return (
            f"TranscodeItem(id={self.id}, path={self.path!r}, "
            f"quality_profile={self.quality_profile!r}, "
            f"original_language={self.original_language!r}, "
            f"status={self.status!r}, worker_id={self.worker_id!r}, attempts={self.attempts})"
        )
