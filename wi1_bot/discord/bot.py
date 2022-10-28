import asyncio
import logging

import discord
from discord.ext import commands

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config

from .cogs import MovieCog, SeriesCog
from .helpers import reply

logger = logging.getLogger(__name__)

bot = commands.Bot(intents=discord.Intents.all(), command_prefix=["!", "."])

radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])


@bot.check
async def check_channel(ctx: commands.Context) -> bool:
    return ctx.channel.id == config["discord"]["channel_id"]


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError) -> None:
    match error:
        case commands.CommandNotFound():
            pass
        case commands.MissingRole():
            await reply(ctx.message, "you don't have permission to do that")
        case commands.MemberNotFound():
            await reply(ctx.message, "that user doesn't exist")
        case commands.MissingRequiredArgument():
            await reply(ctx.message, str(error))
        case _:
            logger.error(error, exc_info=True)
            await reply(
                ctx.message,
                f"something went wrong (<@!{config['discord']['admin_id']}>)",
            )


@bot.event
async def on_ready() -> None:
    if "bot_presence" in config["discord"]:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=config["discord"]["bot_presence"],
            )
        )

    logger.debug("bot is ready")


@bot.before_invoke
async def before_invoke(ctx: commands.Context) -> None:
    logger.debug(f"got command from {ctx.message.author}: {ctx.message.content}")


@commands.cooldown(1, 10)
@bot.command(
    name="downloads", aliases=["queue", "q"], help="see the status of movie downloads"
)
async def downloads_cmd(ctx: commands.Context) -> None:
    async with ctx.typing():
        queue = radarr.get_downloads() + sonarr.get_downloads()

        queue.sort(key=lambda d: (d.timeleft, -d.pct_done))

    if not queue:
        await reply(ctx.message, "there are no pending downloads")
        return

    await reply(ctx.message, "\n\n".join(map(str, queue)), title="download progress")


@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name="quota", help="see your used space on the plex")
async def quota_cmd(ctx: commands.Context) -> None:
    async with ctx.typing():
        used = (
            radarr.get_quota_amount(ctx.message.author.id)
            + sonarr.get_quota_amount(ctx.message.author.id)
        ) / 1024**3

        maximum: float = 0

        try:
            maximum = config["discord"]["quotas"][ctx.message.author.id]
        except KeyError:
            pass

        pct = used / maximum * 100 if maximum != 0 else 100

        msg = (
            f"you have added {used:.2f}/{maximum:.2f} GB ({pct:.1f}%) of useless crap"
            " to the plex"
        )

    await reply(ctx.message, msg)


@commands.cooldown(1, 60)
@bot.command(name="quotas", help="see everyone's used space on the plex")
async def quotas_cmd(ctx: commands.Context) -> None:
    try:
        quotas = config["discord"]["quotas"]
    except ValueError:
        await reply(ctx.message, "quotas are not implemented here")
        return

    if not quotas:
        await reply(ctx.message, "quotas are not implemented here")

    async with ctx.typing():
        msg = []

        for user_id, total in quotas.items():
            used = (
                radarr.get_quota_amount(user_id) + sonarr.get_quota_amount(user_id)
            ) / 1024**3

            pct = used / total * 100 if total != 0 else 100

            user = await bot.fetch_user(user_id)

            msg.append(f"{user.display_name}: {used:.2f}/{total:.2f} GB ({pct:.1f}%)")

    await reply(
        ctx.message,
        "\n".join(sorted(msg)),
        title="quotas of users who have bought space",
    )


@bot.command(name="addtag", help="add a user tag")
@commands.has_role("plex-admin")
async def addtag_cmd(ctx: commands.Context, name: str, user: discord.Member) -> None:
    tag = f"{name}: {user.id}"

    radarr.create_tag(tag)
    sonarr.create_tag(tag)

    await reply(ctx.message, f"tag `{tag}` added for {user.display_name}")


async def run() -> None:
    logger.debug("starting bot")

    async with bot:
        await bot.add_cog(MovieCog(bot))
        await bot.add_cog(SeriesCog(bot))

        await bot.start(config["discord"]["bot_token"])


if __name__ == "__main__":
    logger.addHandler(logging.StreamHandler())

    asyncio.run(run())
