from collections.abc import Generator
from pathlib import Path

import pytest

from wi1_bot.bot import db


@pytest.fixture
def bot_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[None, None, None]:
    monkeypatch.setenv("WB_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(db, "_engine", None)

    db.init_db()

    yield

    monkeypatch.setattr(db, "_engine", None)
