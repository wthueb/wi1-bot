import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from wi1_bot.bot.discord.cogs.notify import NotifyCog
from wi1_bot.bot.models import NotifyMethod, RequestKind
from wi1_bot.bot.notifications import PendingRequest, pending_requests, record_request


def _cog() -> NotifyCog:
    return NotifyCog(MagicMock())


def _req(**overrides: object) -> PendingRequest:
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
    return PendingRequest(**fields)  # type: ignore[arg-type]


def _http_error(cls: type[discord.HTTPException], status: int) -> discord.HTTPException:
    return cls(MagicMock(status=status, reason="err"), "boom")


def test_notify_pings_in_channel() -> None:
    cog = _cog()
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)

    assert asyncio.run(cog._notify(_req())) is True
    channel.send.assert_awaited_once()
    sent = channel.send.await_args
    assert sent is not None
    assert "<@!100>" in sent.args[0]


def test_notify_gives_up_without_usable_channel() -> None:
    cog = _cog()
    cog.bot.get_channel = MagicMock(return_value=None)

    # True => marked notified rather than retried forever
    assert asyncio.run(cog._notify(_req())) is True


def test_notify_retries_on_transient_http_error() -> None:
    cog = _cog()
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(side_effect=_http_error(discord.HTTPException, 500))
    cog.bot.get_channel = MagicMock(return_value=channel)

    # False => not marked notified => retried next poll
    assert asyncio.run(cog._notify(_req())) is False


def test_notify_dms_the_user() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock()
    cog.bot.get_user = MagicMock(return_value=user)

    assert asyncio.run(cog._notify(_req(), NotifyMethod.DM)) is True
    user.send.assert_awaited_once()


def test_notify_falls_back_to_channel_on_forbidden() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock(side_effect=_http_error(discord.Forbidden, 403))
    cog.bot.get_user = MagicMock(return_value=user)

    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    cog.bot.get_channel = MagicMock(return_value=channel)

    assert asyncio.run(cog._notify(_req(), NotifyMethod.DM)) is True
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

    assert asyncio.run(cog._notify(_req(), NotifyMethod.CHANNEL)) is True
    user.send.assert_not_awaited()
    channel.send.assert_awaited_once()


def test_notify_dm_retries_on_transient_http_error() -> None:
    cog = _cog()
    user = MagicMock()
    user.send = AsyncMock(side_effect=_http_error(discord.HTTPException, 500))
    cog.bot.get_user = MagicMock(return_value=user)

    # False => not marked notified => retried next poll
    assert asyncio.run(cog._notify(_req(), NotifyMethod.DM)) is False


def test_notify_gives_up_on_unknown_user() -> None:
    cog = _cog()
    cog.bot.get_user = MagicMock(return_value=None)
    cog.bot.fetch_user = AsyncMock(side_effect=_http_error(discord.NotFound, 404))

    assert asyncio.run(cog._notify(_req(), NotifyMethod.DM)) is True


def test_reconcile_uses_channel_default_for_unset_user(bot_db: None) -> None:
    # a subscriber with no settings row must get the channel mention, not a DM
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="Down (2020)", channel_id=5
    )

    cog = _cog()
    cog.radarr.downloaded_movie_tmdb_ids = MagicMock(return_value={10})
    cog.sonarr.downloaded_series_tvdb_ids = MagicMock(return_value=set())
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    call = cog._notify.await_args
    assert call is not None
    assert call.args[1] == NotifyMethod.CHANNEL


def test_reconcile_only_notifies_downloaded(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="Down (2020)", channel_id=5
    )
    record_request(
        discord_id=2, kind=RequestKind.MOVIE, tmdb_id=20, title="Pending (2021)", channel_id=5
    )
    record_request(
        discord_id=3, kind=RequestKind.SERIES, tvdb_id=30, title="Show (2019)", channel_id=5
    )

    cog = _cog()
    cog.radarr.downloaded_movie_tmdb_ids = MagicMock(return_value={10})
    cog.sonarr.downloaded_series_tvdb_ids = MagicMock(return_value={30})
    cog._notify = AsyncMock(return_value=True)  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    assert cog._notify.await_count == 2
    remaining = pending_requests()
    assert [(p.kind, p.tmdb_id, p.tvdb_id) for p in remaining] == [(RequestKind.MOVIE, 20, None)]


def test_reconcile_keeps_pending_when_notify_fails(bot_db: None) -> None:
    record_request(
        discord_id=1, kind=RequestKind.MOVIE, tmdb_id=10, title="Down (2020)", channel_id=5
    )

    cog = _cog()
    cog.radarr.downloaded_movie_tmdb_ids = MagicMock(return_value={10})
    cog.sonarr.downloaded_series_tvdb_ids = MagicMock(return_value=set())
    cog._notify = AsyncMock(return_value=False)  # transient failure  # type: ignore[method-assign]

    asyncio.run(cog._reconcile())

    assert len(pending_requests()) == 1


def test_reconcile_no_pending_skips_arr(bot_db: None) -> None:
    cog = _cog()
    cog.radarr.downloaded_movie_tmdb_ids = MagicMock()
    cog.sonarr.downloaded_series_tvdb_ids = MagicMock()

    asyncio.run(cog._reconcile())

    cog.radarr.downloaded_movie_tmdb_ids.assert_not_called()
    cog.sonarr.downloaded_series_tvdb_ids.assert_not_called()
