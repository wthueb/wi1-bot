from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TranscodeItem(Base):
    __tablename__ = "transcode_queue"

    id: Mapped[int] = mapped_column(primary_key=True)
    path: Mapped[str]
    languages: Mapped[str | None]
    video_params: Mapped[str | None]
    audio_params: Mapped[str | None]

    def __repr__(self) -> str:
        return (
            f"TranscodeItem(id={self.id}, path={self.path!r}, "
            f"languages={self.languages!r}, video_params={self.video_params!r}, "
            f"audio_params={self.audio_params!r})"
        )
