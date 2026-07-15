import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine

_engine: Engine | None = None


def get_db_path() -> str:
    """Get the database path based on environment variables and standard locations.

    Priority (high to low):
    1. WB_DB_PATH environment variable
    2. $XDG_DATA_HOME/wi1-bot/wi1_bot.db
    3. $HOME/.local/share/wi1-bot/wi1_bot.db
    4. ./wi1_bot.db

    The database directory will be created if it doesn't exist.

    Returns:
        str: The absolute path to the database file
    """
    db_path = os.environ.get("WB_DB_PATH")

    if db_path is None:
        if xdg_data_home := os.getenv("XDG_DATA_HOME"):
            db_dir = Path(xdg_data_home) / "wi1-bot"
        elif home := os.getenv("HOME"):
            db_dir = Path(home) / ".local" / "share" / "wi1-bot"
        else:
            db_dir = Path(".")

        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = str(db_dir / "wi1_bot.db")

    return db_path


def init_db() -> Engine:
    """Initialize the database engine and run migrations.

    This should be called once during application startup.

    Returns:
        Engine: The SQLAlchemy engine instance
    """
    global _engine

    if _engine is not None:
        return _engine

    db_path = get_db_path()
    _engine = create_engine(f"sqlite:///{db_path}")

    wi1_bot_dir = Path(__file__).resolve().parent
    alembic_ini = wi1_bot_dir / "alembic.ini"

    if alembic_ini.exists():
        alembic_cfg = Config(str(alembic_ini))
        command.upgrade(alembic_cfg, "head")
    else:
        raise FileNotFoundError(
            f"alembic.ini not found at {alembic_ini}. Database migrations cannot be run."
        )

    return _engine


def get_engine() -> Engine:
    """Get the initialized database engine.

    Returns:
        Engine: The SQLAlchemy engine instance

    Raises:
        RuntimeError: If init_db() has not been called yet
    """
    if _engine is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return _engine
