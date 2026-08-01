from wi1_bot.bot.models import RequestKind
from wi1_bot.bot.notifications import (
    mark_notified,
    pending_requests,
    record_request,
    remove_request,
)


def test_record_and_pending(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix (1999)", channel_id=42
    )

    pending = pending_requests()

    assert len(pending) == 1
    p = pending[0]
    assert p.discord_id == 1
    assert p.kind == RequestKind.MOVIE
    assert p.tmdb_id == 603
    assert p.tvdb_id is None
    assert p.title == "The Matrix (1999)"
    assert p.channel_id == 42


def test_series_request_uses_tvdb(bot_db: None) -> None:
    record_request(
        discord_id=7, kind=RequestKind.SERIES, tvdb_id=121361, title="GoT (2011)", channel_id=1
    )

    p = pending_requests()[0]
    assert p.kind == RequestKind.SERIES
    assert p.tvdb_id == 121361
    assert p.tmdb_id is None


def test_mark_notified_removes_from_pending(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=1, title="A", channel_id=1)
    record_request(discord_id=2, kind=RequestKind.SERIES, tvdb_id=2, title="B", channel_id=1)

    ids = [p.id for p in pending_requests()]
    mark_notified([ids[0]])

    remaining = pending_requests()
    assert [p.id for p in remaining] == [ids[1]]


def test_mark_notified_empty_is_noop(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=1, title="A", channel_id=1)

    mark_notified([])

    assert len(pending_requests()) == 1


def test_record_request_is_idempotent_for_pending(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix", channel_id=1
    )
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix", channel_id=9
    )

    assert len(pending_requests()) == 1

    record_request(
        discord_id=2, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix", channel_id=1
    )
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=604, title="The Matrix 2", channel_id=1
    )
    assert len(pending_requests()) == 3


def test_remove_request_drops_pending(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="A", channel_id=1)
    record_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=20, title="B", channel_id=1)

    removed = remove_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10)

    assert removed == 1
    assert [(p.kind, p.tvdb_id) for p in pending_requests()] == [(RequestKind.SERIES, 20)]


def test_remove_request_leaves_other_users(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="A", channel_id=1)
    record_request(discord_id=2, kind=RequestKind.MOVIE, tmdb_id=10, title="A", channel_id=1)

    removed = remove_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10)

    assert removed == 1
    assert [p.discord_id for p in pending_requests()] == [2]
