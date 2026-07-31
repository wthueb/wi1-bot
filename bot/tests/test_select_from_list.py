import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from wi1_bot.bot.discord import helpers
from wi1_bot.bot.discord.helpers import SelectCancelled, select_from_list
from wi1_bot.bot.settings import set_auto_select_single


def _msg() -> MagicMock:
    msg = MagicMock()
    msg.author.id = 100
    return msg


def test_single_result_auto_selected_by_default(bot_db: None) -> None:
    bot = MagicMock()
    bot.wait_for = AsyncMock()  # must not be reached
    msg = _msg()

    selected, resp = asyncio.run(select_from_list(bot, msg, ["only"]))

    assert selected == ["only"]
    assert resp is msg
    bot.wait_for.assert_not_awaited()


def test_single_result_prompts_when_autoselect_off(
    bot_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_auto_select_single(100, False)
    monkeypatch.setattr(helpers, "reply", AsyncMock())

    cancel = MagicMock()
    cancel.content = "c"
    bot = MagicMock()
    bot.wait_for = AsyncMock(return_value=cancel)

    with pytest.raises(SelectCancelled):
        asyncio.run(select_from_list(bot, _msg(), ["only"]))

    bot.wait_for.assert_awaited_once()


def test_allow_auto_select_false_forces_picker(
    bot_db: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(helpers, "reply", AsyncMock())

    cancel = MagicMock()
    cancel.content = "c"
    bot = MagicMock()
    bot.wait_for = AsyncMock(return_value=cancel)

    with pytest.raises(SelectCancelled):
        asyncio.run(select_from_list(bot, _msg(), ["only"], allow_auto_select=False))

    bot.wait_for.assert_awaited_once()


def test_multiple_results_always_prompt(bot_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(helpers, "reply", AsyncMock())

    pick = MagicMock()
    pick.content = "2"
    bot = MagicMock()
    bot.wait_for = AsyncMock(return_value=pick)

    selected, resp = asyncio.run(select_from_list(bot, _msg(), ["a", "b"]))

    assert selected == ["b"]
    bot.wait_for.assert_awaited_once()


def test_multi_pick_with_spaces_after_commas(bot_db: None, monkeypatch: pytest.MonkeyPatch) -> None:
    # "1, 3" (spaces after commas) is how people naturally type it; it must be accepted,
    # not silently ignored until the prompt times out
    monkeypatch.setattr(helpers, "reply", AsyncMock())

    pick = MagicMock()
    pick.content = "1, 3"
    bot = MagicMock()
    bot.wait_for = AsyncMock(return_value=pick)

    selected, resp = asyncio.run(select_from_list(bot, _msg(), ["a", "b", "c"]))

    assert selected == ["a", "c"]
    bot.wait_for.assert_awaited_once()
