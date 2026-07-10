from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TranscodeItem(Base):
    __tablename__ = "transcode_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str]
    quality_profile: Mapped[str]
    original_language: Mapped[str | None]

    def __repr__(self) -> str:
        return (
            f"TranscodeItem(id={self.id}, path={self.path!r}, "
            f"quality_profile={self.quality_profile!r}, "
            f"original_language={self.original_language!r})"
        )
