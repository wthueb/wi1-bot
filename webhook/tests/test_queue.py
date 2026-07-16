from datetime import timedelta

import pytest
from sqlalchemy.orm import Session

from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_engine
from wi1_bot.webhook.models import TranscodeItem
from wi1_bot.webhook.transcode_queue import TranscodeQueue, _utcnow


@pytest.fixture
def queue(db: None) -> TranscodeQueue:
    q = TranscodeQueue()
    q.clear()
    return q


def test_add_returns_new_job_id(queue: TranscodeQueue) -> None:
    job_id = queue.add("/movies/a.mkv", "good")
    assert isinstance(job_id, int)

    item = queue.claim("w")
    assert item is not None
    assert item.id == job_id


def test_add_and_claim(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good", "English")
    assert queue.size == 1

    item = queue.claim("worker-1")
    assert item is not None
    assert item.path == "/movies/a.mkv"
    assert item.quality_profile == "good"
    assert item.original_language == "English"
    assert item.worker_id == "worker-1"
    assert item.attempts == 1

    # a claimed job is not handed out again
    assert queue.claim("worker-2") is None


def test_claim_empty_returns_none(queue: TranscodeQueue) -> None:
    assert queue.claim("w") is None


def test_claim_is_fifo(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")
    queue.add("/movies/b.mkv", "good")

    first = queue.claim("w")
    second = queue.claim("w")
    assert first is not None and second is not None
    assert first.path == "/movies/a.mkv"
    assert second.path == "/movies/b.mkv"


def test_complete_removes_and_returns_path(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")
    item = queue.claim("w")
    assert item is not None

    assert queue.complete(item.id) == "/movies/a.mkv"
    assert queue.size == 0


def test_fail_retry_requeues(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")
    item = queue.claim("w")
    assert item is not None

    assert queue.fail(item.id, retry=True) is None
    assert queue.size == 1

    # requeued -> claimable again
    again = queue.claim("w")
    assert again is not None
    assert again.attempts == 2


def test_fail_no_retry_drops_and_returns_path(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")
    item = queue.claim("w")
    assert item is not None

    assert queue.fail(item.id, retry=False) == "/movies/a.mkv"
    assert queue.size == 0


def test_fail_retry_drops_after_max_attempts(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")

    result: str | None = None
    for _ in range(3):
        item = queue.claim("w")
        assert item is not None
        result = queue.fail(item.id, retry=True)

    # each claim bumps attempts; after MAX_ATTEMPTS the retry drops the job
    assert result == "/movies/a.mkv"
    assert queue.size == 0


def test_expired_lease_is_reclaimed(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")
    item = queue.claim("worker-1")
    assert item is not None

    # force the lease into the past
    with Session(get_engine()) as session:
        db_item = session.get(TranscodeItem, item.id)
        assert db_item is not None
        db_item.lease_expires_at = _utcnow() - timedelta(seconds=1)
        session.commit()

    reclaimed = queue.claim("worker-2")
    assert reclaimed is not None
    assert reclaimed.id == item.id
    assert reclaimed.worker_id == "worker-2"
    assert reclaimed.attempts == 2


def test_heartbeat_extends_only_for_owner(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")
    item = queue.claim("worker-1")
    assert item is not None

    assert queue.heartbeat(item.id, "worker-1") is True
    assert queue.heartbeat(item.id, "worker-2") is False


def test_claim_lease_secs_can_be_overridden(queue: TranscodeQueue) -> None:
    queue.add("/movies/a.mkv", "good")

    before = _utcnow()
    item = queue.claim("w", lease_secs=5)
    assert item is not None
    assert item.lease_expires_at is not None
    assert timedelta(seconds=4) <= item.lease_expires_at - before <= timedelta(seconds=6)


def test_claim_lease_defaults_to_configured_value(
    queue: TranscodeQueue, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config.webhook, "lease_secs", 42)
    queue.add("/movies/a.mkv", "good")

    before = _utcnow()
    item = queue.claim("w")
    assert item is not None
    assert item.lease_expires_at is not None
    assert timedelta(seconds=41) <= item.lease_expires_at - before <= timedelta(seconds=43)
