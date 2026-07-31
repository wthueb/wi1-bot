import pytest

from wi1_bot.bot.models import NotifyMethod
from wi1_bot.bot.settings import (
    DEFAULT_AUTO_NOTIFY,
    DEFAULT_AUTO_SELECT_SINGLE,
    DEFAULT_NOTIFY_METHOD,
    get_notify_methods,
    get_settings,
    set_auto_notify,
    set_auto_select_single,
    set_notify_method,
)


def test_get_settings_defaults_when_unset(bot_db: None) -> None:
    prefs = get_settings(discord_id=100)
    assert prefs.notify_method == DEFAULT_NOTIFY_METHOD == NotifyMethod.CHANNEL


def test_set_and_get_notify_method(bot_db: None) -> None:
    set_notify_method(100, NotifyMethod.CHANNEL)
    assert get_settings(100).notify_method == NotifyMethod.CHANNEL


def test_set_notify_method_upserts(bot_db: None) -> None:
    set_notify_method(100, NotifyMethod.CHANNEL)
    set_notify_method(100, NotifyMethod.DM)  # a second write updates the same row
    assert get_settings(100).notify_method == NotifyMethod.DM


def test_set_notify_method_rejects_unknown(bot_db: None) -> None:
    with pytest.raises(ValueError):
        set_notify_method(100, "carrier-pigeon")


def test_get_notify_methods_returns_only_set_users(bot_db: None) -> None:
    set_notify_method(1, NotifyMethod.CHANNEL)
    set_notify_method(2, NotifyMethod.DM)

    methods = get_notify_methods([1, 2, 3])
    assert methods == {1: NotifyMethod.CHANNEL, 2: NotifyMethod.DM}


def test_get_notify_methods_empty_input(bot_db: None) -> None:
    assert get_notify_methods([]) == {}


def test_auto_select_defaults_on(bot_db: None) -> None:
    assert get_settings(100).auto_select_single is DEFAULT_AUTO_SELECT_SINGLE is True


def test_set_auto_select_single(bot_db: None) -> None:
    set_auto_select_single(100, False)
    assert get_settings(100).auto_select_single is False
    set_auto_select_single(100, True)  # upserts the same row
    assert get_settings(100).auto_select_single is True


def test_auto_notify_defaults_off(bot_db: None) -> None:
    assert get_settings(100).auto_notify is DEFAULT_AUTO_NOTIFY is False


def test_set_auto_notify(bot_db: None) -> None:
    set_auto_notify(100, True)
    assert get_settings(100).auto_notify is True
    set_auto_notify(100, False)
    assert get_settings(100).auto_notify is False


def test_settings_are_independent(bot_db: None) -> None:
    set_auto_select_single(100, False)
    assert get_settings(100).notify_method == DEFAULT_NOTIFY_METHOD
    assert get_settings(100).auto_notify is False

    set_notify_method(100, NotifyMethod.CHANNEL)
    set_auto_notify(100, True)
    assert get_settings(100).auto_select_single is False
    assert get_settings(100).notify_method == NotifyMethod.CHANNEL
    assert get_settings(100).auto_notify is True
