from asyncio import sleep
import multiprocessing
import logging
import logging.handlers
import re

import discord
from discord.ext import commands
import yaml

from radarr import Radarr, Movie
import push


with open("config.yaml", "rb") as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

logger = logging.getLogger("wi1-bot.bot")
logger.setLevel(logging.DEBUG)

radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])

bot = commands.Bot(intents=discord.Intents.all(), command_prefix=["!", "."])


async def member_has_role(member: discord.Member | discord.User, role: str) -> bool:
    if isinstance(member, discord.Member):
        return role in [r.name for r in member.roles]

    return False


async def reply(
    msg: discord.Message, content: str, title: str = "", error: bool = False
) -> None:
    if len(content) > 2048:
        content = content[:2045] + "..."

    embed = discord.Embed(
        title=title,
        description=content,
        color=discord.Color.red() if error else discord.Color.blue(),
    )

    await msg.reply(embed=embed)


async def select_movies(
    msg: discord.Message, command: str, movies: list[Movie]
) -> tuple[discord.Message, list[Movie]]:
    movie_list = [f"{i+1}. {movie}" for i, movie in enumerate(movies)]

    await reply(
        msg,
        "\n".join(movie_list),
        title=(
            "type in the number of the movie (or multiple separated by commas), or type"
            " c to cancel"
        ),
    )

    def check(resp: discord.Message):
        if resp.author != msg.author or resp.channel != msg.channel:
            return False

        regex = re.compile(r"^(c|(\d+,?)+|[!.]addmovie .*)$", re.IGNORECASE)

        if re.match(regex, resp.content.strip()):
            return True

        return False

    try:
        resp = await bot.wait_for("message", check=check, timeout=30)
    except Exception:
        await reply(msg, f"timed out, {command} cancelled", error=True)
        return msg, []

    if resp.content.strip().lower() == "c":
        await reply(resp, f"{command} cancelled")
        return resp, []

    if resp.content.strip()[1:].startswith("addmovie"):
        return resp, []

    idxs = [int(i) for i in resp.content.strip().split(",") if i.isdigit()]

    for idx in idxs:
        if idx < 1 or idx > len(movies):
            await reply(resp, f"invalid index ({idx}), {command} cancelled", error=True)
            return resp, []

    selected = []

    for idx in idxs:
        selected.append(movies[idx - 1])

    return resp, selected


@bot.event
async def on_ready():
    try:
        await bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=config["discord"]["bot_presence"],
            )
        )
    except Exception:
        pass

    logger.debug("bot is ready")


@bot.command(name="addmovie", help="add a movie to the plex")
async def addmovie_cmd(ctx: commands.Context, *, query: str = ''):
    if ctx.channel.id != config["discord"]["channel_id"]:
        return

    if not query:
        await reply(ctx.message, "usage: !addmovie KEYWORDS...")
        return

    logger.debug(
        f"got !addmovie command from user {ctx.message.author.name}:"
        f" {ctx.message.content}"
    )

    async with ctx.typing():
        movies = radarr.lookup_movie(query)

        if not movies:
            await reply(
                ctx.message,
                f"could not find a movie matching the query: {query}",
                error=True,
            )
            return

    resp, to_add = await select_movies(ctx.message, "addmovie", movies)

    if not to_add:
        return

    added = []

    for movie in to_add:
        if not radarr.add_movie(movie):
            if radarr.movie_downloaded(movie):
                await reply(resp, f"{movie} is already DOWNLOADED on the plex (idiot)")
            else:
                await reply(resp, f"{movie} is already on the plex (idiot)")
            continue

        added.append(movie)

        logger.info(
            f"{ctx.message.author.name} has added the movie {movie.full_title} to the"
            " plex"
        )

        push.send(
            f"{ctx.message.author.name} has added the movie {movie.full_title}",
            url=movie.url,
        )

        await reply(resp, f"added movie {movie} to the plex")

    await sleep(10)

    if not radarr.add_tag(added, ctx.message.author.id):
        push.send(
            f"get {ctx.message.author.name} a tag", title="tag needed", priority=1
        )

        await ctx.send(f"hey <@!{config['discord']['admin_id']}> get this guy a tag")


@bot.command(name="delmovie", help="delete a movie from the plex")
async def delmovie_cmd(ctx: commands.Context, *, query: str = ''):
    if ctx.channel.id != config["discord"]["channel_id"]:
        return

    if not query:
        await reply(ctx.message, "usage: !delmovie KEYWORDS...")
        return

    logger.debug(
        f"got !delmovie command from user {ctx.message.author.name}:"
        f" {ctx.message.content}"
    )

    async with ctx.typing():
        if await member_has_role(ctx.message.author, "plex-admin"):
            movies = radarr.lookup_library(query)[:50]
        else:
            movies = radarr.lookup_user_movies(query, ctx.message.author.id)[:50]

        if not movies:
            if await member_has_role(ctx.message.author, "plex-admin"):
                await reply(
                    ctx.message,
                    f"could not find a movie matching the query: {query}",
                    error=True,
                )
            else:
                await reply(
                    ctx.message,
                    f"you haven't added a movie matching the query: {query}",
                    error=True,
                )

            return

    resp, to_delete = await select_movies(ctx.message, "delmovie", movies)

    if not to_delete:
        return

    for movie in to_delete:
        radarr.del_movie(movie)

        logger.info(
            f"{ctx.message.author.name} has deleted the movie {movie.full_title} from"
            " the plex"
        )

        push.send(
            f"{ctx.message.author.name} has deleted the movie {movie.full_title}",
            url=movie.url,
        )

        await reply(resp, f"deleted movie {movie} from the plex")


@commands.cooldown(1, 10)  # one time every 10 seconds
@bot.command(
    name="downloads", aliases=["queue", "q"], help="see the status of movie downloads"
)
async def downloads_cmd(ctx: commands.Context):
    if ctx.channel.id != config["discord"]["channel_id"]:
        return

    async with ctx.typing():
        queue = radarr.get_downloads()

    if not queue:
        await reply(ctx.message, "there are no pending downloads")
        return

    await reply(ctx.message, "\n\n".join(map(str, queue)), title="download progress")


@commands.cooldown(1, 60)
@bot.command(
    name="searchmissing", help="search for missing movies that have been added"
)
async def searchmissing_cmd(ctx: commands.Context):
    if ctx.channel.id != config["discord"]["channel_id"]:
        return

    if await member_has_role(ctx.message.author, "plex-admin"):
        await reply(
            ctx.message,
            f"user {ctx.message.author.name} does not have permission to use this"
            " command",
            error=True,
        )
        return

    radarr.search_missing()

    await reply(ctx.message, "searching for missing movies...")


@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name="quota", help="see your used space on the plex")
async def quota_cmd(ctx: commands.Context):
    if ctx.channel.id != config["discord"]["channel_id"]:
        return

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
async def quotas_cmd(ctx: commands.Context):
    if ctx.channel.id != config["discord"]["channel_id"]:
        return

    if "quotas" not in config["discord"]:
        await reply(ctx.message, "quotas are not implemented here")

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


if __name__ == "__main__":
    logger.addHandler(logging.StreamHandler())
    bot.run(config["discord"]["bot_token"])
