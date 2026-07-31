import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from wi1_bot.bot.discord.cogs import settings as settings_cog
from wi1_bot.bot.discord.cogs.settings import SettingsCog
from wi1_bot.bot.models import NotifyMethod
from wi1_bot.bot.settings import get_settings


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.author.id = 100
    ctx.author.name = "tester"
    return ctx


@pytest.fixture(autouse=True)
def _quiet_reply(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    stub = AsyncMock()
    monkeypatch.setattr(settings_cog, "reply", stub)
    return stub


def test_set_notify_persists_method(bot_db: None) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_notify(_ctx(), NotifyMethod.CHANNEL))
    assert get_settings(100).notify_method == NotifyMethod.CHANNEL


def test_set_notify_rejects_bad_value(bot_db: None, _quiet_reply: AsyncMock) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_notify(_ctx(), "smoke-signal"))

    assert get_settings(100).notify_method == NotifyMethod.CHANNEL  # unchanged default
    call = _quiet_reply.await_args
    assert call is not None
    assert call.kwargs.get("error") is True


def test_set_autoselect_off(bot_db: None) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_autoselect(_ctx(), "off"))
    assert get_settings(100).auto_select_single is False


def test_set_autoselect_accepts_synonyms(bot_db: None) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_autoselect(_ctx(), "disable"))
    assert get_settings(100).auto_select_single is False
    asyncio.run(cog._set_autoselect(_ctx(), "YES"))  # case-insensitive
    assert get_settings(100).auto_select_single is True


def test_set_autoselect_rejects_bad_value(bot_db: None, _quiet_reply: AsyncMock) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_autoselect(_ctx(), "maybe"))

    assert get_settings(100).auto_select_single is True  # unchanged default
    call = _quiet_reply.await_args
    assert call is not None
    assert call.kwargs.get("error") is True


def test_set_autonotify_on(bot_db: None) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_autonotify(_ctx(), "on"))
    assert get_settings(100).auto_notify is True


def test_set_autonotify_rejects_bad_value(bot_db: None, _quiet_reply: AsyncMock) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._set_autonotify(_ctx(), "sometimes"))

    assert get_settings(100).auto_notify is False  # unchanged default
    call = _quiet_reply.await_args
    assert call is not None
    assert call.kwargs.get("error") is True


def test_show_settings_lists_current(bot_db: None, _quiet_reply: AsyncMock) -> None:
    cog = SettingsCog(MagicMock())
    asyncio.run(cog._show_settings(_ctx()))

    call = _quiet_reply.await_args
    assert call is not None
    body = call.args[1]
    assert "in the request channel" in body  # notify default, rendered human-readably
    assert "auto-select single result" in body
    assert "auto-notify on your additions" in body
    assert "**off**" in body  # auto-notify default
