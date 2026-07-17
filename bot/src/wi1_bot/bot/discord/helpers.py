import asyncio
import re
from collections.abc import Callable
from typing import TypeVar

import discord
from discord.ext import commands

from wi1_bot.arr import MediaState

# suffix appended to a choice in an add-list so users can see, before they pick, whether
# a title is already downloaded ("on plex") or monitored (queued to download). ABSENT
# titles get nothing so they read as a normal search result.
STATE_SUFFIX: dict[MediaState, str] = {
    MediaState.ABSENT: "",
    MediaState.MONITORED: " — *monitored*",
    MediaState.DOWNLOADED: " — **on plex**",
}


async def member_has_role(member: discord.Member | discord.User, role: str) -> bool:
    if isinstance(member, discord.Member):
        return role in [r.name for r in member.roles]

    return False


async def reply(msg: discord.Message, content: str, title: str = "", error: bool = False) -> None:
    if len(content) > 2048:
        while len(content) > 2048 - len("\n..."):
            content = content[: content.rfind("\n")].rstrip()

        content += "\n..."

    embed = discord.Embed(
        title=title,
        description=content,
        color=discord.Color.red() if error else discord.Color.blue(),
    )

    await msg.reply(embed=embed)


T = TypeVar("T")


class SelectError(Exception):
    """base class for errors raised by select_from_list."""


class SelectTimeout(SelectError):
    """raised when the user does not make a selection in time."""


class SelectCancelled(SelectError):
    """raised when the user cancels the selection."""

    def __init__(self, resp: discord.Message) -> None:
        self.resp = resp


class SelectInvalidIndex(SelectError):
    """raised when the user picks an index that is out of range."""

    def __init__(self, index: int, resp: discord.Message) -> None:
        self.index = index
        self.resp = resp


async def select_from_list(
    bot: commands.Bot,
    msg: discord.Message,
    choices: list[T],
    render: Callable[[T], str] = str,
) -> tuple[list[T], discord.Message]:
    choices_text = "\n".join(f"{i + 1}. {render(choice)}" for i, choice in enumerate(choices))

    await reply(
        msg,
        choices_text,
        title=(
            "type in the number of the choice (or multiple separated by commas), or"
            " type c to cancel"
        ),
    )

    def check(resp: discord.Message) -> bool:
        if resp.author != msg.author or resp.channel != msg.channel:
            return False

        # c, idxs, or new command
        regex = re.compile(r"^(c|(\d+,?)+|[!.].+ .*)$", re.IGNORECASE)

        return bool(re.match(regex, resp.content.strip()))

    try:
        resp = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        raise SelectTimeout from None

    content = resp.content.strip()

    if content.lower() == "c":
        raise SelectCancelled(resp)

    # the user typed a new command instead of picking; abandon this selection
    # silently and let the new command run
    if content[0] in (".", "!"):
        return [], resp

    selected: list[T] = []

    for i in content.split(","):
        if not i.isdigit():
            continue

        idx = int(i)

        if idx < 1 or idx > len(choices):
            raise SelectInvalidIndex(idx, resp)

        selected.append(choices[idx - 1])

    return selected, resp
