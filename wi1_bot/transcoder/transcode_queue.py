from sqlalchemy.orm import Session

from wi1_bot.db import get_engine
from wi1_bot.models import TranscodeItem

__all__ = ["TranscodeItem", "TranscodeQueue", "queue"]


class TranscodeQueue:
    def add(
        self,
        path: str,
        languages: str | None = None,
        video_params: str | None = None,
        audio_params: str | None = None,
    ) -> None:
        engine = get_engine()
        with Session(engine) as session:
            item = TranscodeItem(
                path=path,
                languages=languages,
                video_params=video_params,
                audio_params=audio_params,
            )
            session.add(item)
            session.commit()

    def get_one(self) -> TranscodeItem | None:
        engine = get_engine()
        with Session(engine) as session:
            item = session.query(TranscodeItem).order_by(TranscodeItem.id).first()

            if item is None:
                return None

            session.expunge(item)
            return item

    def remove(self, item: TranscodeItem) -> None:
        engine = get_engine()
        with Session(engine) as session:
            merged_item = session.merge(item)
            session.delete(merged_item)
            session.commit()

    def clear(self) -> None:
        engine = get_engine()
        with Session(engine) as session:
            session.query(TranscodeItem).delete()
            session.commit()

    @property
    def size(self) -> int:
        engine = get_engine()
        with Session(engine) as session:
            return session.query(TranscodeItem).count()


queue = TranscodeQueue()
