import asyncio
import logging
import re

import discord
from discord.ext import commands

from wi1_bot import push
from wi1_bot.arr.radarr import Movie, Radarr
from wi1_bot.config import config
from wi1_bot.helpers import member_has_role, reply


class MovieCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])

    @commands.command(name="addmovie", help="add a movie to the plex")
    async def addmovie_cmd(self, ctx: commands.Context, *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !addmovie KEYWORDS...")
            return

        self.logger.debug(
            f"got command from {ctx.message.author}: {ctx.message.content}"
        )

        async with ctx.typing():
            movies = self.radarr.lookup_movie(query)

            if not movies:
                await reply(
                    ctx.message,
                    f"could not find a movie matching the query: {query}",
                    error=True,
                )
                return

        resp, to_add = await self._select_movies(ctx.message, "addmovie", movies)

        if not to_add:
            return

        added: list[Movie] = []

        for movie in to_add:
            if not self.radarr.add_movie(movie):
                if self.radarr.movie_downloaded(movie):
                    await reply(
                        resp, f"{movie} is already DOWNLOADED on the plex (idiot)"
                    )
                else:
                    await reply(resp, f"{movie} is already on the plex (idiot)")
                continue

            self.logger.info(
                f"{ctx.message.author.name} has added the movie {movie.full_title} to"
                " the plex"
            )

            push.send(
                f"{ctx.message.author.name} has added the movie {movie.full_title}",
                url=movie.url,
            )

            await reply(resp, f"added movie {movie} to the plex")

            added.append(movie)

        if not added:
            return

        await asyncio.sleep(10)

        if not self.radarr.add_tag(added, ctx.message.author.id):
            push.send(
                f"get {ctx.message.author.name} a tag", title="tag needed", priority=1
            )

            await ctx.send(
                f"hey <@!{config['discord']['admin_id']}> get this guy a tag"
            )

    @commands.command(name="delmovie", help="delete a movie from the plex")
    async def delmovie_cmd(self, ctx: commands.Context, *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !delmovie KEYWORDS...")
            return

        self.logger.debug(
            f"got command from {ctx.message.author}: {ctx.message.content}"
        )

        async with ctx.typing():
            if await member_has_role(ctx.message.author, "plex-admin"):
                movies = self.radarr.lookup_library(query)[:50]

                if not movies:
                    await reply(
                        ctx.message,
                        f"could not find a movie matching the query: {query}",
                        error=True,
                    )
                    return
            else:
                movies = self.radarr.lookup_user_movies(query, ctx.message.author.id)[
                    :50
                ]

                if not movies:
                    await reply(
                        ctx.message,
                        f"you haven't added a movie matching the query: {query}",
                        error=True,
                    )
                    return

        resp, to_delete = await self._select_movies(ctx.message, "delmovie", movies)

        if not to_delete:
            return

        for movie in to_delete:
            self.radarr.del_movie(movie)

            self.logger.info(
                f"{ctx.message.author.name} has deleted the movie"
                f" {movie.full_title} from the plex"
            )

            push.send(
                f"{ctx.message.author.name} has deleted the movie {movie.full_title}",
                url=movie.url,
            )

            await reply(resp, f"deleted movie {movie} from the plex")

    async def _select_movies(
        self, msg: discord.Message, command: str, movies: list[Movie]
    ) -> tuple[discord.Message, list[Movie]]:
        movie_list = [f"{i+1}. {movie}" for i, movie in enumerate(movies)]

        await reply(
            msg,
            "\n".join(movie_list),
            title=(
                "type in the number of the movie (or multiple separated by commas), or"
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
            resp = await self.bot.wait_for("message", check=check, timeout=30)
        except asyncio.TimeoutError:
            await reply(msg, f"timed out, {command} cancelled", error=True)
            return msg, []

        if resp.content.strip().lower() == "c":
            await reply(resp, f"{command} cancelled")
            return resp, []

        if resp.content.strip()[0] in [".", "!"]:
            return resp, []

        choices = resp.content.strip().split(",")

        idxs = [int(i) for i in choices if i.isdigit()]

        selected = []

        for idx in idxs:
            if idx < 1 or idx > len(movies):
                await reply(
                    resp, f"invalid index ({idx}), {command} cancelled", error=True
                )
                return resp, []

            selected.append(movies[idx - 1])

        return resp, selected
