from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from wi1_bot.bot.db import get_engine
from wi1_bot.bot.models import NotifyMethod, UserSettings, utcnow

DEFAULT_NOTIFY_METHOD = NotifyMethod.CHANNEL

NOTIFY_METHOD_LABELS = {
    NotifyMethod.DM: "direct message",
    NotifyMethod.CHANNEL: "in the request channel",
}

DEFAULT_AUTO_SELECT_SINGLE = True
DEFAULT_AUTO_NOTIFY = False


@dataclass
class UserPreferences:
    discord_id: int
    notify_method: NotifyMethod
    auto_select_single: bool
    auto_notify: bool


def get_settings(discord_id: int) -> UserPreferences:
    with Session(get_engine()) as session:
        row = session.get(UserSettings, discord_id)
        if row is None:
            return UserPreferences(
                discord_id=discord_id,
                notify_method=DEFAULT_NOTIFY_METHOD,
                auto_select_single=DEFAULT_AUTO_SELECT_SINGLE,
                auto_notify=DEFAULT_AUTO_NOTIFY,
            )
        return UserPreferences(
            discord_id=discord_id,
            notify_method=NotifyMethod(row.notify_method),
            auto_select_single=row.auto_select_single,
            auto_notify=row.auto_notify,
        )


def get_notify_methods(discord_ids: Iterable[int]) -> dict[int, NotifyMethod]:
    ids = list(discord_ids)
    if not ids:
        return {}

    with Session(get_engine()) as session:
        rows = session.execute(
            select(UserSettings.discord_id, UserSettings.notify_method).where(
                UserSettings.discord_id.in_(ids)
            )
        ).all()
        return {discord_id: NotifyMethod(method) for discord_id, method in rows}


def set_notify_method(discord_id: int, method: str | NotifyMethod) -> None:
    # NotifyMethod() raises ValueError on an unknown method
    _upsert(discord_id, notify_method=NotifyMethod(method))


def set_auto_select_single(discord_id: int, value: bool) -> None:
    _upsert(discord_id, auto_select_single=value)


def set_auto_notify(discord_id: int, value: bool) -> None:
    _upsert(discord_id, auto_notify=value)


def _upsert(discord_id: int, **values: object) -> None:
    with Session(get_engine()) as session:
        row = session.get(UserSettings, discord_id)
        if row is None:
            session.add(UserSettings(discord_id=discord_id, **values))
        else:
            for key, value in values.items():
                setattr(row, key, value)
            row.updated_at = utcnow()
        session.commit()
