import os
import pathlib

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from .models import TranscodeItem

__all__ = ["TranscodeItem", "TranscodeQueue", "queue"]


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

        self._db_path = db_path
        self._engine = create_engine(f"sqlite:///{db_path}")
        self._migrations_run = False

    def _ensure_migrations(self) -> None:
        """Ensure migrations have been run (called on first database access)."""
        if not self._migrations_run:
            self._run_migrations()
            self._migrations_run = True

    def _run_migrations(self) -> None:
        """Run Alembic migrations to upgrade the database schema."""
        # Find alembic.ini in the wi1_bot package
        wi1_bot_dir = pathlib.Path(__file__).resolve().parent.parent
        alembic_ini = wi1_bot_dir / "alembic.ini"
        if alembic_ini.exists():
            alembic_cfg = Config(str(alembic_ini))
            command.upgrade(alembic_cfg, "head")
        else:
            raise FileNotFoundError(
                f"alembic.ini not found at {alembic_ini}. Database migrations cannot be run."
            )

    def add(
        self,
        path: str,
        languages: str | None = None,
        video_params: str | None = None,
        audio_params: str | None = None,
    ) -> None:
        self._ensure_migrations()
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
        self._ensure_migrations()
        with Session(self._engine) as session:
            item = session.query(TranscodeItem).order_by(TranscodeItem.id).first()

            if item is None:
                return None

            session.expunge(item)
            return item

    def remove(self, item: TranscodeItem) -> None:
        self._ensure_migrations()
        if item.id is None:
            raise ValueError("Cannot remove item without an id")

        with Session(self._engine) as session:
            merged_item = session.merge(item)
            session.delete(merged_item)
            session.commit()

    def clear(self) -> None:
        self._ensure_migrations()
        with Session(self._engine) as session:
            session.query(TranscodeItem).delete()
            session.commit()

    @property
    def size(self) -> int:
        self._ensure_migrations()
        with Session(self._engine) as session:
            return session.query(TranscodeItem).count()


queue = TranscodeQueue()
