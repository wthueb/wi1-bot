import os
import pathlib

from sqlalchemy import String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


class Base(DeclarativeBase):
    pass


class TranscodeItem(Base):
    __tablename__ = "transcode_queue"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String, nullable=False)
    languages: Mapped[str | None] = mapped_column(String, nullable=True)
    video_params: Mapped[str | None] = mapped_column(String, nullable=True)
    audio_params: Mapped[str | None] = mapped_column(String, nullable=True)

    def __repr__(self) -> str:
        return (
            f"TranscodeItem(id={self.id}, path={self.path!r}, "
            f"languages={self.languages!r}, video_params={self.video_params!r}, "
            f"audio_params={self.audio_params!r})"
        )


class TranscodeQueue:
    def __init__(self) -> None:
        db_path = os.environ.get("WB_DB_PATH")

        if db_path is None:
            if xdg_data_home := os.getenv("XDG_DATA_HOME"):
                db_dir = pathlib.Path(xdg_data_home) / "wi1-bot"
            elif home := os.getenv("HOME"):
                db_dir = pathlib.Path(home) / ".local" / "share" / "wi1-bot"
            else:
                db_dir = pathlib.Path(".")

            db_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(db_dir / "wi1_bot.db")

        self._engine = create_engine(f"sqlite:///{db_path}")

        Base.metadata.create_all(self._engine)

    def add(
        self,
        path: str,
        languages: str | None = None,
        video_params: str | None = None,
        audio_params: str | None = None,
    ) -> None:
        with Session(self._engine) as session:
            item = TranscodeItem(
                path=path,
                languages=languages,
                video_params=video_params,
                audio_params=audio_params,
            )
            session.add(item)
            session.commit()

    def get_one(self) -> TranscodeItem | None:
        with Session(self._engine) as session:
            item = session.query(TranscodeItem).order_by(TranscodeItem.id).first()

            if item is None:
                return None

            session.expunge(item)
            return item

    def remove(self, item: TranscodeItem) -> None:
        if item.id is None:
            raise ValueError("Cannot remove item without an id")

        with Session(self._engine) as session:
            merged_item = session.merge(item)
            session.delete(merged_item)
            session.commit()

    def clear(self) -> None:
        with Session(self._engine) as session:
            session.query(TranscodeItem).delete()
            session.commit()

    @property
    def size(self) -> int:
        with Session(self._engine) as session:
            return session.query(TranscodeItem).count()


queue = TranscodeQueue()
