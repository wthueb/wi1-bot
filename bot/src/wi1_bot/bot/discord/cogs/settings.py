import asyncio
from collections.abc import Callable

import structlog
from discord.ext import commands

from wi1_bot.bot.models import NotifyMethod
from wi1_bot.bot.settings import (
    NOTIFY_METHOD_LABELS,
    UserPreferences,
    get_settings,
    set_auto_notify,
    set_auto_select_single,
    set_notify_method,
)

from ..helpers import reply

logger = structlog.get_logger(__name__)

_BOOL_WORDS = {
    "on": True,
    "off": False,
    "enable": True,
    "disable": False,
    "enabled": True,
    "disabled": False,
    "true": True,
    "false": False,
    "yes": True,
    "no": False,
}


def _on_off(value: bool) -> str:
    return "on" if value else "off"


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="settings",
        aliases=["config"],
        help="view or change your settings, e.g. !settings notify channel",
    )
    async def settings_cmd(
        self, ctx: commands.Context[commands.Bot], setting: str = "", *, value: str = ""
    ) -> None:
        setting = setting.strip().lower()

        if not setting:
            await self._show_settings(ctx)
        elif setting == "notify":
            await self._set_notify(ctx, value)
        elif setting == "autoselect":
            await self._set_autoselect(ctx, value)
        elif setting == "autonotify":
            await self._set_autonotify(ctx, value)
        else:
            await reply(
                ctx.message,
                f"unknown setting: {setting}\navailable settings: notify, autoselect, autonotify",
                error=True,
            )

    async def _show_settings(self, ctx: commands.Context[commands.Bot]) -> None:
        prefs = await asyncio.to_thread(get_settings, ctx.author.id)

        lines = [
            f"- notifications: **{NOTIFY_METHOD_LABELS[prefs.notify_method]}**"
            " (change with `!settings notify <dm|channel>`)",
            f"- auto-select single result: **{_on_off(prefs.auto_select_single)}**"
            " (change with `!settings autoselect <on|off>`)",
            f"- auto-notify on your additions: **{_on_off(prefs.auto_notify)}**"
            " (change with `!settings autonotify <on|off>`)",
        ]
        await reply(ctx.message, "\n".join(lines), title="your settings")

    async def _set_notify(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        try:
            method = NotifyMethod(value.strip().lower())
        except ValueError:
            current = await asyncio.to_thread(get_settings, ctx.author.id)
            await reply(
                ctx.message,
                f"usage: !settings notify <dm|channel>\ncurrently:"
                f" {NOTIFY_METHOD_LABELS[current.notify_method]}",
                error=True,
            )
            return

        await asyncio.to_thread(set_notify_method, ctx.author.id, method)
        logger.info("notify method changed", user=ctx.author.name, method=method)
        await reply(
            ctx.message,
            f"you'll now be notified by {NOTIFY_METHOD_LABELS[method]} when your titles land",
            title="settings updated",
        )

    async def _set_autoselect(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        await self._set_bool(
            ctx,
            value,
            name="autoselect",
            setter=set_auto_select_single,
            current=lambda p: p.auto_select_single,
            confirm=lambda on: (
                f"single-result auto-select is now {_on_off(on)}"
                + ("" if on else " — you'll always see the picker")
            ),
        )

    async def _set_autonotify(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        await self._set_bool(
            ctx,
            value,
            name="autonotify",
            setter=set_auto_notify,
            current=lambda p: p.auto_notify,
            confirm=lambda on: (
                "auto-notify is now on — you'll be notified on your own additions"
                if on
                else "auto-notify is now off — react with the bell to be notified"
            ),
        )

    async def _set_bool(
        self,
        ctx: commands.Context[commands.Bot],
        value: str,
        *,
        name: str,
        setter: Callable[[int, bool], None],
        current: Callable[[UserPreferences], bool],
        confirm: Callable[[bool], str],
    ) -> None:
        choice = _BOOL_WORDS.get(value.strip().lower())

        if choice is None:
            prefs = await asyncio.to_thread(get_settings, ctx.author.id)
            await reply(
                ctx.message,
                f"usage: !settings {name} <on|off>\ncurrently: {_on_off(current(prefs))}",
                error=True,
            )
            return

        await asyncio.to_thread(setter, ctx.author.id, choice)
        logger.info("setting changed", user=ctx.author.name, setting=name, value=choice)
        await reply(ctx.message, confirm(choice), title="settings updated")
