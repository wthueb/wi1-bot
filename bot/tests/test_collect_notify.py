import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord

from wi1_bot.bot.discord.helpers import (
    NOTIFY_EMOJI,
    UNNOTIFY_EMOJI,
    collect_reaction_choices,
)


def _user(uid: int) -> MagicMock:
    user = MagicMock()
    user.id = uid
    user.bot = False
    return user


def _reaction(emoji: str) -> MagicMock:
    reaction = MagicMock()
    reaction.emoji = emoji
    return reaction


def _msg() -> MagicMock:
    msg = MagicMock()
    msg.add_reaction = AsyncMock()
    msg.remove_reaction = AsyncMock()
    return msg


def _bot(*events: object) -> MagicMock:
    bot = MagicMock()
    bot.user = MagicMock()
    bot.wait_for = AsyncMock(side_effect=[*events, asyncio.TimeoutError()])
    return bot


def test_single_emoji_collects_distinct_reactors() -> None:
    bot = _bot(
        (_reaction(NOTIFY_EMOJI), _user(1)),
        (_reaction(NOTIFY_EMOJI), _user(1)),  # duplicate, ignored
        (_reaction(NOTIFY_EMOJI), _user(2)),
    )
    msg = _msg()

    subscribed: list[int] = []

    async def on_notify(user: discord.Member | discord.User) -> None:
        subscribed.append(user.id)

    asyncio.run(collect_reaction_choices(bot, msg, {NOTIFY_EMOJI: on_notify}, timeout=5))

    assert subscribed == [1, 2]
    msg.add_reaction.assert_awaited_once()  # one seed for one emoji
    msg.remove_reaction.assert_awaited_once()


def test_two_emojis_dispatch_to_the_right_handler() -> None:
    bot = _bot(
        (_reaction(NOTIFY_EMOJI), _user(1)),  # user 1 subscribes
        (_reaction(UNNOTIFY_EMOJI), _user(2)),  # user 2 unsubscribes
        (_reaction(UNNOTIFY_EMOJI), _user(1)),  # user 1 also unsubscribes (distinct emoji)
    )
    msg = _msg()

    subscribed: list[int] = []
    unsubscribed: list[int] = []

    async def on_notify(user: discord.Member | discord.User) -> None:
        subscribed.append(user.id)

    async def on_unnotify(user: discord.Member | discord.User) -> None:
        unsubscribed.append(user.id)

    asyncio.run(
        collect_reaction_choices(
            bot, msg, {NOTIFY_EMOJI: on_notify, UNNOTIFY_EMOJI: on_unnotify}, timeout=5
        )
    )

    assert subscribed == [1]
    assert unsubscribed == [2, 1]
    assert msg.add_reaction.await_count == 2  # a seed per emoji
    assert msg.remove_reaction.await_count == 2


def test_no_reactors_still_removes_seed() -> None:
    bot = _bot()
    msg = _msg()

    async def on_notify(user: discord.Member | discord.User) -> None:
        raise AssertionError("should not be called")

    asyncio.run(collect_reaction_choices(bot, msg, {NOTIFY_EMOJI: on_notify}, timeout=5))

    msg.remove_reaction.assert_awaited_once()
