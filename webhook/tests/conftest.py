from collections.abc import Iterator
from pathlib import Path

import pytest

import wi1_bot.webhook.db as db_mod


@pytest.fixture
def db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Give each test a fresh, migrated SQLite database at a temp path."""
    monkeypatch.setenv("WB_DB_PATH", str(tmp_path / "test.db"))
    db_mod._engine = None
    db_mod.init_db()
    yield
    db_mod._engine = None
