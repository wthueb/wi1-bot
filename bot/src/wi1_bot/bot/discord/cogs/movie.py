import asyncio
import logging

from discord.ext import commands

from wi1_bot.arr.radarr import Movie, Radarr
from wi1_bot.bot.config import config
from wi1_bot.common import push

from ..helpers import (
    STATE_SUFFIX,
    SelectCancelled,
    SelectInvalidIndex,
    SelectTimeout,
    member_has_role,
    reply,
    select_from_list,
)


class MovieCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.radarr = Radarr.from_config(config.radarr)

    @commands.command(name="addmovie", help="add a movie to the plex")
    async def addmovie_cmd(self, ctx: commands.Context[commands.Bot], *, query: str = "") -> None:
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

            # resolve each result's state up front so the picker can show what's already
            # on plex / monitored before the user commits to adding it
            states = {movie: self.radarr.movie_state(movie) for movie in potential}

        try:
            to_add, resp = await select_from_list(
                self.bot,
                ctx.message,
                potential,
                render=lambda movie: f"{movie}{STATE_SUFFIX[states[movie]]}",
            )
        except SelectTimeout:
            await reply(ctx.message, "timed out, addmovie cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "addmovie cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), addmovie cancelled", error=True)
            return

        if not to_add:
            return

        added: list[Movie] = []

        for movie in to_add:
            if not self.radarr.add_movie(movie):
                if self.radarr.movie_downloaded(movie):
                    await reply(resp, f"{movie} is already DOWNLOADED on the plex (idiot)")
                else:
                    await reply(resp, f"{movie} is already on the plex (idiot)")
                continue

            self.logger.info(f"{ctx.message.author.name} has added the movie {movie.full_title}")

            push.send(
                config.pushover,
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
                config.pushover,
                f"get {ctx.message.author.name} a tag",
                title="tag needed",
                priority=1,
            )

            await ctx.send(f"hey <@!{config.discord.admin_id}> get this guy a tag")

    @commands.command(name="delmovie", help="delete a movie from the plex")
    async def delmovie_cmd(self, ctx: commands.Context[commands.Bot], *, query: str = "") -> None:
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
                potential = self.radarr.lookup_user_library(query, ctx.message.author.id)[:50]

                if not potential:
                    await reply(
                        ctx.message,
                        f"you haven't added a movie matching the query: {query}",
                        error=True,
                    )
                    return

        try:
            to_delete, resp = await select_from_list(self.bot, ctx.message, potential)
        except SelectTimeout:
            await reply(ctx.message, "timed out, delmovie cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "delmovie cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), delmovie cancelled", error=True)
            return

        if not to_delete:
            return

        for movie in to_delete:
            self.radarr.del_movie(movie)

            self.logger.info(f"{ctx.message.author.name} has deleted the movie {movie.full_title}")

            push.send(
                config.pushover,
                f"{ctx.message.author.name} has deleted the movie {movie.full_title}",
                url=movie.url,
            )

            await reply(resp, f"deleted movie {movie} from the plex")
