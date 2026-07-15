import asyncio
import re
from typing import TypeVar

import discord
from discord.ext import commands


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


async def select_from_list(
    bot: commands.Bot, msg: discord.Message, command: str, choices: list[T]
) -> tuple[discord.Message, list[T]]:
    choices_text = "\n".join(f"{i + 1}. {choice}" for i, choice in enumerate(choices))

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

        if re.match(regex, resp.content.strip()):
            return True

        return False

    try:
        resp = await bot.wait_for("message", check=check, timeout=30)
    except asyncio.TimeoutError:
        await reply(msg, f"timed out, {command} cancelled", error=True)
        return msg, []

    if resp.content.strip().lower() == "c":
        await reply(resp, f"{command} cancelled")
        return resp, []

    if resp.content.strip()[0] in [".", "!"]:
        return resp, []

    idxs = [int(i) for i in resp.content.strip().split(",") if i.isdigit()]

    selected: list[T] = []

    for idx in idxs:
        if idx < 1 or idx > len(choices):
            await reply(resp, f"invalid index ({idx}), {command} cancelled", error=True)
            return resp, []

        selected.append(choices[idx - 1])

    return resp, selected
