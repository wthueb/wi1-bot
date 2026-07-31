import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

_engine: Engine | None = None

_DB_FILENAME = "wi1_bot_discord.db"


def get_db_path() -> str:
    db_path = os.environ.get("WB_DB_PATH")

    if db_path is None:
        if xdg_data_home := os.getenv("XDG_DATA_HOME"):
            db_dir = Path(xdg_data_home) / "wi1-bot"
        elif home := os.getenv("HOME"):
            db_dir = Path(home) / ".local" / "share" / "wi1-bot"
        else:
            db_dir = Path(".")

        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(db_dir / _DB_FILENAME)

    return db_path


def init_db() -> Engine:
    global _engine

    if _engine is not None:
        return _engine

    db_path = get_db_path()
    _engine = create_engine(f"sqlite:///{db_path}")

    bot_dir = Path(__file__).resolve().parent
    alembic_ini = bot_dir / "alembic.ini"

    if alembic_ini.exists():
        alembic_cfg = Config(str(alembic_ini))
        command.upgrade(alembic_cfg, "head")
    else:
        raise FileNotFoundError(
            f"alembic.ini not found at {alembic_ini}. Database migrations cannot run."
        )

    return _engine


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
