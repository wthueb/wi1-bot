import asyncio
import logging

from discord.ext import commands

from wi1_bot import push
from wi1_bot.arr.radarr import Movie, Radarr
from wi1_bot.config import config

from ..helpers import member_has_role, reply, select_from_list


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

        async with ctx.typing():
            potential = self.radarr.lookup_movie(query)

            if not potential:
                await reply(
                    ctx.message,
                    f"could not find a movie matching the query: {query}",
                    error=True,
                )
                return

        resp, to_add = await select_from_list(
            self.bot, ctx.message, "addmovie", potential
        )

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
                f"{ctx.message.author.name} has added the movie {movie.full_title}"
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

        async with ctx.typing():
            if await member_has_role(ctx.message.author, "plex-admin"):
                potential = self.radarr.lookup_library(query)[:50]

                if not potential:
                    await reply(
                        ctx.message,
                        f"could not find a movie matching the query: {query}",
                        error=True,
                    )
                    return
            else:
                potential = self.radarr.lookup_user_movies(
                    query, ctx.message.author.id
                )[:50]

                if not potential:
                    await reply(
                        ctx.message,
                        f"you haven't added a movie matching the query: {query}",
                        error=True,
                    )
                    return

        resp, to_delete = await select_from_list(
            self.bot, ctx.message, "delmovie", potential
        )

        if not to_delete:
            return

        for movie in to_delete:
            self.radarr.del_movie(movie)

            self.logger.info(
                f"{ctx.message.author.name} has deleted the movie {movie.full_title}"
            )

            push.send(
                f"{ctx.message.author.name} has deleted the movie {movie.full_title}",
                url=movie.url,
            )

            await reply(resp, f"deleted movie {movie} from the plex")
