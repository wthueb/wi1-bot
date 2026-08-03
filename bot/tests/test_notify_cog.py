import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from wi1_bot.arr.episode import Episode
from wi1_bot.bot.discord.cogs.notify import NotifyCog
from wi1_bot.bot.models import NotifyMethod, RequestKind
from wi1_bot.bot.notifications import (
    ActiveRequest,
    active_requests,
    record_request,
    remove_request,
    seen_episode_ids,
)


def _cog() -> NotifyCog:
    return NotifyCog(MagicMock())


def _req(**overrides: object) -> ActiveRequest:
    fields: dict = {
        "id": 1,
        "discord_id": 100,
        "kind": RequestKind.MOVIE,
        "tmdb_id": 1,
        "tvdb_id": None,
        "title": "A Movie (2020)",
        "channel_id": 9,
    }
    fields.update(overrides)
    return ActiveRequest(**fields)  # type: ignore[arg-type]


def _ep(ep_id: int, season: int, num: int, title: str = "Ep") -> Episode:
    return Episode(
        {
            "id": ep_id,
            "seasonNumber": season,
            "episodeNumber": num,
            "title": title,
            "airDate": "2026-01-01",
        },
        series_title="Show",
        series_tvdb_id=30,
        series_imdb_id="",
    )


def _http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(MagicMock(status=status, reason="err"), "boom")


MESSAGE = "**A Movie (2020)** is now on plex!"


def test_notify_pings_in_channel() -> None:
    cog = _cog()
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)

    assert asyncio.run(cog._notify(_req(), MESSAGE)) is True
    channel.send.assert_awaited_once()
    sent = channel.send.await_args
    assert sent is not None
    assert "<@!100>" in sent.args[0]


def test_notify_gives_up_without_usable_channel() -> None:
    cog = _cog()
    cog.bot.get_channel = MagicMock(return_value=None)

    # True => marked notified rather than retried forever
    assert asyncio.run(cog._notify(_req(), MESSAGE)) is True


def test_notify_retries_on_transient_http_error() -> None:
    cog = _cog()
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(side_effect=_http_error(discord.HTTPException, 500))
    cog.bot.get_channel = MagicMock(return_value=channel)

    # False => not marked notified => retried next poll
    assert asyncio.run(cog._notify(_req(), MESSAGE)) is False


def test_notify_dms_the_user() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock()
    cog.bot.get_user = MagicMock(return_value=user)

    assert asyncio.run(cog._notify(_req(), MESSAGE, NotifyMethod.DM)) is True
    user.send.assert_awaited_once()


def test_notify_falls_back_to_channel_on_forbidden() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock(side_effect=_http_error(discord.Forbidden, 403))
    cog.bot.get_user = MagicMock(return_value=user)

    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)

    assert asyncio.run(cog._notify(_req(), MESSAGE, NotifyMethod.DM)) is True
    channel.send.assert_awaited_once()
    sent = channel.send.await_args
    assert sent is not None
    assert "<@!100>" in sent.args[0]


def test_notify_channel_preference_skips_dm() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock()
    cog.bot.get_user = MagicMock(return_value=user)

    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)

    assert asyncio.run(cog._notify(_req(), MESSAGE, NotifyMethod.CHANNEL)) is True
    user.send.assert_not_awaited()
    channel.send.assert_awaited_once()


def test_notify_dm_retries_on_transient_http_error() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock(side_effect=_http_error(discord.HTTPException, 500))
    cog.bot.get_user = MagicMock(return_value=user)

    # False => not marked notified => retried next poll
    assert asyncio.run(cog._notify(_req(), MESSAGE, NotifyMethod.DM)) is False


def test_notify_gives_up_on_unknown_user() -> None:
    cog = _cog()
    cog.bot.get_user = MagicMock(return_value=None)
    cog.bot.fetch_user = AsyncMock(side_effect=_http_error(discord.NotFound, 404))

    assert asyncio.run(cog._notify(_req(), MESSAGE, NotifyMethod.DM)) is True


def _mock_arrs(
    cog: NotifyCog,
    movie_ids: set[int] | None = None,
    episodes: dict[int, list[Episode]] | None = None,
) -> None:
    cog.radarr.downloaded_movie_tmdb_ids = MagicMock(return_value=movie_ids or set())
    cog.sonarr.downloaded_episodes_by_tvdb_id = MagicMock(return_value=episodes or {})


def test_reconcile_uses_channel_default_for_unset_user(bot_db: None) -> None:
    # a subscriber with no settings row must get the channel mention, not a DM
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="Down (2020)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, movie_ids={10})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    call = cog._notify.await_args
    assert call is not None
    assert call.args[2] == NotifyMethod.CHANNEL


def test_reconcile_only_notifies_downloaded_movies(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="Down (2020)", channel_id=5
    )
    record_request(
        discord_id=2, kind=RequestKind.MOVIE, tmdb_id=20, title="Pending (2021)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, movie_ids={10})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    assert cog._notify.await_count == 1
    remaining = active_requests()
    assert [(a.kind, a.tmdb_id) for a in remaining] == [(RequestKind.MOVIE, 20)]


def test_reconcile_keeps_pending_when_notify_fails(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="Down (2020)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, movie_ids={10})
    cog._notify = AsyncMock(return_value=False)  # transient failure  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    assert len(active_requests()) == 1
    assert active_requests()[0].notified is False


def test_reconcile_no_active_skips_arr(bot_db: None) -> None:
    cog = _cog()
    cog.radarr.downloaded_movie_tmdb_ids = MagicMock()
    cog.sonarr.downloaded_episodes_by_tvdb_id = MagicMock()

    asyncio.run(cog._reconcile())

    cog.radarr.downloaded_movie_tmdb_ids.assert_not_called()
    cog.sonarr.downloaded_episodes_by_tvdb_id.assert_not_called()


def test_series_first_notification_announces_the_show(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1), _ep(102, 1, 2)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    call = cog._notify.await_args
    assert call is not None
    assert call.args[1] == "There are 2 episodes of **Show (2019)** already on plex!"

    # the subscription stays active, flagged notified, with current episodes seeded
    active = active_requests()
    assert len(active) == 1
    assert active[0].notified is True
    assert seen_episode_ids(30) == {101, 102}

    # the same episodes must not notify again next poll
    cog._notify.reset_mock()
    asyncio.run(cog._reconcile())
    cog._notify.assert_not_awaited()


def test_series_undownloaded_show_waits(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: []})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    cog._notify.assert_not_awaited()
    assert active_requests()[0].notified is False


def test_series_new_episode_announced_once_per_show(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]
    asyncio.run(cog._reconcile())
    cog._notify.reset_mock()

    # three new episodes land within one poll: one message, newest named, rest counted
    _mock_arrs(
        cog,
        episodes={30: [_ep(101, 1, 1), _ep(102, 1, 2), _ep(103, 1, 3, "Finale")]},
    )
    asyncio.run(cog._reconcile())

    cog._notify.assert_awaited_once()
    call = cog._notify.await_args
    assert call is not None
    assert call.args[1] == "**Show S01E03 - Finale** is now on plex! (+1 more episode)"
    assert seen_episode_ids(30) == {101, 102, 103}


def test_series_single_new_episode_has_no_count(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]
    asyncio.run(cog._reconcile())
    cog._notify.reset_mock()

    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1), _ep(102, 1, 2, "Next")]})
    asyncio.run(cog._reconcile())

    cog._notify.assert_awaited_once()
    call = cog._notify.await_args
    assert call is not None
    assert call.args[1] == "**Show S01E02 - Next** is now on plex!"


def test_series_each_show_announces_separately(bot_db: None) -> None:
    # a sunday-night drop across shows yields one message per show, not one total
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=40, title="Other (2021)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1)], 40: [_ep(201, 2, 1)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]
    asyncio.run(cog._reconcile())
    cog._notify.reset_mock()

    _mock_arrs(
        cog,
        episodes={
            30: [_ep(101, 1, 1), _ep(102, 1, 2)],
            40: [_ep(201, 2, 1), _ep(202, 2, 2)],
        },
    )
    asyncio.run(cog._reconcile())

    assert cog._notify.await_count == 2


def test_new_subscriber_to_established_show_gets_initial_message(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]
    asyncio.run(cog._reconcile())
    cog._notify.reset_mock()

    # a second user subscribes after the show is already on plex
    record_request(
        discord_id=2, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )
    asyncio.run(cog._reconcile())

    cog._notify.assert_awaited_once()
    call = cog._notify.await_args
    assert call is not None
    assert call.args[0].discord_id == 2
    assert call.args[1] == "there is 1 episode of **Show (2019)** already on plex!"


def test_series_episode_send_failure_still_marks_seen(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]
    asyncio.run(cog._reconcile())

    cog._notify = AsyncMock(return_value=False)  # type: ignore[method-assign]
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1), _ep(102, 1, 2)]})
    asyncio.run(cog._reconcile())

    # episode announcements are best effort; the episode is consumed either way
    assert seen_episode_ids(30) == {101, 102}


def test_series_missing_from_sonarr_keeps_subscription(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    cog._notify.assert_not_awaited()
    assert len(active_requests()) == 1


def test_reconcile_prunes_seen_state_of_unsubscribed_shows(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    _mock_arrs(cog, episodes={30: [_ep(101, 1, 1)]})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]
    asyncio.run(cog._reconcile())
    assert seen_episode_ids(30) == {101}

    remove_request(discord_id=1, kind=RequestKind.SERIES, tvdb_id=30)
    asyncio.run(cog._reconcile())

    assert seen_episode_ids(30) == set()
