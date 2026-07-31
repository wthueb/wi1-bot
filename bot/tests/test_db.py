import pytest
from sqlalchemy import inspect

from wi1_bot.bot import db


def test_init_db_runs_migrations(bot_db: None) -> None:
    tables = set(inspect(db.get_engine()).get_table_names())

    assert {"requests", "leaderboard", "alembic_version"} <= tables


def test_get_engine_requires_init(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(db, "_engine", None)

    with pytest.raises(RuntimeError):
        db.get_engine()
