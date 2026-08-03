from wi1_bot.bot.models import RequestKind
from wi1_bot.bot.notifications import (
    active_requests,
    mark_episodes_seen,
    mark_notified,
    prune_seen_episodes,
    record_request,
    remove_request,
    seen_episode_ids,
)


def test_record_and_active(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix (1999)", channel_id=42
    )

    active = active_requests()

    assert len(active) == 1
    a = active[0]
    assert a.discord_id == 1
    assert a.kind == RequestKind.MOVIE
    assert a.tmdb_id == 603
    assert a.tvdb_id is None
    assert a.title == "The Matrix (1999)"
    assert a.channel_id == 42
    assert a.notified is False


def test_series_request_uses_tvdb(bot_db: None) -> None:
    record_request(
        discord_id=7, kind=RequestKind.SERIES, tvdb_id=121361, title="GoT (2011)", channel_id=1
    )

    a = active_requests()[0]
    assert a.kind == RequestKind.SERIES
    assert a.tvdb_id == 121361
    assert a.tmdb_id is None


def test_mark_notified_completes_movie(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=1, title="A", channel_id=1)
    record_request(discord_id=2, kind=RequestKind.MOVIE, tmdb_id=2, title="B", channel_id=1)

    ids = [a.id for a in active_requests()]
    mark_notified([ids[0]])

    remaining = active_requests()
    assert [a.id for a in remaining] == [ids[1]]


def test_mark_notified_keeps_series_active(bot_db: None) -> None:
    # a series subscription is standing: notification only flips the notified flag
    record_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=10, title="A", channel_id=1)

    mark_notified([a.id for a in active_requests()])

    active = active_requests()
    assert len(active) == 1
    assert active[0].notified is True


def test_mark_notified_empty_is_noop(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=1, title="A", channel_id=1)

    mark_notified([])

    assert len(active_requests()) == 1


def test_record_request_is_idempotent_for_active(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix", channel_id=1
    )
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix", channel_id=9
    )

    assert len(active_requests()) == 1

    record_request(
        discord_id=2, kind=RequestKind.MOVIE, tmdb_id=603, title="The Matrix", channel_id=1
    )
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=604, title="The Matrix 2", channel_id=1
    )
    assert len(active_requests()) == 3


def test_record_series_idempotent_after_notified(bot_db: None) -> None:
    # re-subscribing to a show that already notified must not create a second row
    record_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=10, title="A", channel_id=1)
    mark_notified([a.id for a in active_requests()])

    record_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=10, title="A", channel_id=1)

    assert len(active_requests()) == 1


def test_remove_request_drops_active(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="A", channel_id=1)
    record_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=20, title="B", channel_id=1)

    removed = remove_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10)

    assert removed == 1
    assert [(a.kind, a.tvdb_id) for a in active_requests()] == [(RequestKind.SERIES, 20)]


def test_remove_series_after_notified(bot_db: None) -> None:
    # unsubscribing must work even after the initial notification went out
    record_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=10, title="A", channel_id=1)
    mark_notified([a.id for a in active_requests()])

    removed = remove_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=10)

    assert removed == 1
    assert active_requests() == []


def test_remove_request_leaves_other_users(bot_db: None) -> None:
    record_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="A", channel_id=1)
    record_request(discord_id=2, kind=RequestKind.MOVIE, tmdb_id=10, title="A", channel_id=1)

    removed = remove_request(discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10)

    assert removed == 1
    assert [a.discord_id for a in active_requests()] == [2]


def test_seen_episodes_roundtrip(bot_db: None) -> None:
    assert seen_episode_ids(10) == set()

    mark_episodes_seen(10, [1, 2, 3])
    mark_episodes_seen(10, [3, 4])  # overlapping ids must not raise
    mark_episodes_seen(20, [1])

    assert seen_episode_ids(10) == {1, 2, 3, 4}
    assert seen_episode_ids(20) == {1}


def test_mark_episodes_seen_empty_is_noop(bot_db: None) -> None:
    mark_episodes_seen(10, [])

    assert seen_episode_ids(10) == set()


def test_prune_seen_episodes_drops_unsubscribed(bot_db: None) -> None:
    mark_episodes_seen(10, [1])
    mark_episodes_seen(20, [2])

    prune_seen_episodes({10})

    assert seen_episode_ids(10) == {1}
    assert seen_episode_ids(20) == set()


def test_prune_seen_episodes_empty_drops_all(bot_db: None) -> None:
    mark_episodes_seen(10, [1])

    prune_seen_episodes(set())

    assert seen_episode_ids(10) == set()
