import multiprocessing
import logging
import logging.handlers

import discord
from discord.ext import commands

from cogs import MovieCog
from config import config
from helpers import reply
from radarr import Radarr


logger = logging.getLogger("wi1-bot.bot")
logger.setLevel(logging.DEBUG)

bot = commands.Bot(intents=discord.Intents.all(), command_prefix=["!", "."])

radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])


@bot.check
async def check_channel(ctx: commands.Context) -> bool:
    return ctx.channel.id == config["discord"]["channel_id"]


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


@commands.cooldown(1, 10)  # one time every 10 seconds
@bot.command(
    name="downloads", aliases=["queue", "q"], help="see the status of movie downloads"
)
async def downloads_cmd(ctx: commands.Context) -> None:
    async with ctx.typing():
        queue = radarr.get_downloads()

    if not queue:
        await reply(ctx.message, "there are no pending downloads")
        return

    await reply(ctx.message, "\n\n".join(map(str, queue)), title="download progress")


@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name="quota", help="see your used space on the plex")
async def quota_cmd(ctx: commands.Context) -> None:
    async with ctx.typing():
        used = radarr.get_quota_amount(ctx.message.author.id) / 1024 ** 3

        maximum = 0

        try:
            maximum = config["discord"]["quotas"][ctx.message.author.id]
        except Exception:
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
    if "quotas" not in config["discord"]:
        await reply(ctx.message, "quotas are not implemented here")
        return

    quotas = config["discord"]["quotas"]

    if not quotas:
        await reply(ctx.message, "quotas are not implemented here")

    async with ctx.typing():
        msg = []

        for user_id, total in quotas.items():
            used = radarr.get_quota_amount(user_id) / 1024 ** 3

            pct = used / total * 100 if total != 0 else 100

            user = await bot.fetch_user(user_id)

            msg.append(f"{user.display_name}: {used:.2f}/{total:.2f} GB ({pct:.1f}%)")

    await reply(
        ctx.message,
        "\n".join(sorted(msg)),
        title="quotas of users who have bought space",
    )


def run(logging_queue: multiprocessing.Queue) -> None:
    queue_handler = logging.handlers.QueueHandler(logging_queue)

    logger.addHandler(queue_handler)

    logger.debug("starting bot")

    bot.run(config["discord"]["bot_token"])


bot.add_cog(MovieCog(bot))


if __name__ == "__main__":
    logger.addHandler(logging.StreamHandler())

    bot.run(config["discord"]["bot_token"])
