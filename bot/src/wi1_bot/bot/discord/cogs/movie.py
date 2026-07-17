import asyncio
import logging

import discord
import requests
from discord.ext import commands

from wi1_bot.arr import MediaState
from wi1_bot.arr.radarr import Movie, Radarr
from wi1_bot.bot.config import config
from wi1_bot.bot.tmdb import MAX_CAST, Credits, Person, Tmdb
from wi1_bot.common import push

from ..helpers import (
    REQUEST_EMOJI,
    STATE_LABEL,
    STATE_SUFFIX,
    SelectCancelled,
    SelectInvalidIndex,
    SelectTimeout,
    format_runtime,
    member_has_role,
    reply,
    select_from_list,
    wait_for_request_reaction,
)


class MovieCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.radarr = Radarr.from_config(config.radarr)
        self.tmdb = Tmdb.from_config(config.tmdb)

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

        await self._add_movies(resp, to_add, ctx.message.author)

    async def _add_movies(
        self,
        resp: discord.Message,
        to_add: list[Movie],
        requester: discord.Member | discord.User,
        announce_requester: bool = False,
    ) -> None:
        added: list[Movie] = []

        for movie in to_add:
            if not self.radarr.add_movie(movie):
                if self.radarr.movie_downloaded(movie):
                    await reply(resp, f"{movie} is already DOWNLOADED on the plex (idiot)")
                else:
                    await reply(resp, f"{movie} is already on the plex (idiot)")
                continue

            self.logger.info(f"{requester.name} has added the movie {movie.full_title}")

            push.send(
                config.pushover,
                f"{requester.name} has added the movie {movie.full_title}",
                url=movie.url,
            )

            msg = f"added movie {movie} to the plex"

            if announce_requester:
                msg += f" (requested by {requester.display_name})"

            await reply(resp, msg)

            added.append(movie)

        if not added:
            return

        await asyncio.sleep(10)

        if not self.radarr.add_tag(added, requester.id):
            push.send(
                config.pushover,
                f"get {requester.name} a tag",
                title="tag needed",
                priority=1,
            )

            await resp.channel.send(f"hey <@!{config.discord.admin_id}> get this guy a tag")

    @commands.command(name="movieinfo", help="get information about a movie")
    async def movieinfo_cmd(self, ctx: commands.Context[commands.Bot], *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !movieinfo KEYWORDS...")
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
            # on plex / monitored before the user commits to selecting it
            states = {movie: self.radarr.movie_state(movie) for movie in potential}

        try:
            selected, resp = await select_from_list(
                self.bot,
                ctx.message,
                potential,
                render=lambda movie: f"{movie}{STATE_SUFFIX[states[movie]]}",
            )
        except SelectTimeout:
            await reply(ctx.message, "timed out, movieinfo cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "movieinfo cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), movieinfo cancelled", error=True)
            return

        if not selected:
            return

        offers: list[asyncio.Task[None]] = []

        for movie in selected:
            async with ctx.typing():
                state = states[movie]
                embed = self._build_movie_embed(movie, state)

            info_msg = await resp.reply(embed=embed)

            if state is MediaState.ABSENT:
                # each offer waits for a request reaction; run them as tasks so
                # multiple selections don't wait serially
                offers.append(asyncio.create_task(self._offer_movie_request(info_msg, movie)))

        if offers:
            await asyncio.gather(*offers)

    async def _offer_movie_request(self, info_msg: discord.Message, movie: Movie) -> None:
        user = await wait_for_request_reaction(self.bot, info_msg)

        if user is None:
            return

        self.logger.info(f"{user.name} requested the movie {movie.full_title} via reaction")

        await self._add_movies(info_msg, [movie], user, announce_requester=True)

    def _movie_credits(self, movie: Movie) -> Credits | None:
        if self.tmdb is not None:
            try:
                return self.tmdb.movie_credits(movie.tmdb_id)
            except requests.RequestException:
                self.logger.warning(
                    f"failed to fetch tmdb credits for {movie.full_title}", exc_info=True
                )

        # without tmdb, radarr itself stores credits for library movies (only tmdb
        # person links though, no imdb ids)
        if "id" not in movie.json:
            return None

        credits = self.radarr.get_movie_credits(movie.json["id"])

        directors = [
            Person(c["personName"], c["personTmdbId"])
            for c in credits
            if c["type"] == "crew" and c.get("job") == "Director"
        ]
        cast = sorted((c for c in credits if c["type"] == "cast"), key=lambda c: c.get("order", 0))

        return Credits(
            directors=directors,
            cast=[Person(c["personName"], c["personTmdbId"]) for c in cast[:MAX_CAST]],
        )

    def _build_movie_embed(self, movie: Movie, state: MediaState) -> discord.Embed:
        json = movie.json

        overview: str = json.get("overview", "")

        embed = discord.Embed(
            title=movie.full_title,
            url=movie.url,
            description=overview[:1024],
            color=discord.Color.blue(),
        )

        if poster := json.get("remotePoster"):
            embed.set_thumbnail(url=poster)

        if runtime := json.get("runtime"):
            embed.add_field(name="runtime", value=format_runtime(runtime), inline=False)

        if genres := json.get("genres"):
            embed.add_field(name="genres", value=", ".join(genres), inline=False)

        if studio := json.get("studio"):
            embed.add_field(name="studio", value=studio, inline=False)

        if certification := json.get("certification"):
            embed.add_field(name="rated", value=certification, inline=False)

        ratings = json.get("ratings") or {}
        rating_parts: list[str] = []

        # sources with no rating yet report value 0, so filter those out too
        if (imdb := ratings.get("imdb")) and imdb["value"]:
            rating_parts.append(f"imdb {imdb['value']:.1f}/10")
        if (tmdb := ratings.get("tmdb")) and tmdb["value"]:
            rating_parts.append(f"tmdb {tmdb['value']:.1f}/10")
        if (rt := ratings.get("rottenTomatoes")) and rt["value"]:
            rating_parts.append(f"rt {rt['value']:.0f}%")
        if (metacritic := ratings.get("metacritic")) and metacritic["value"]:
            rating_parts.append(f"metacritic {metacritic['value']:.0f}/100")

        embed.add_field(
            name="ratings",
            value=" | ".join(rating_parts) if rating_parts else "unrated",
            inline=False,
        )

        if credits := self._movie_credits(movie):
            if credits.directors:
                embed.add_field(
                    name="director", value=", ".join(map(str, credits.directors)), inline=False
                )
            if credits.cast:
                embed.add_field(name="cast", value=", ".join(map(str, credits.cast)), inline=False)

        embed.add_field(name="status", value=STATE_LABEL[state], inline=False)

        if state is MediaState.DOWNLOADED:
            detail = self.radarr.get_movie_by_id(json["id"])

            if movie_file := detail.get("movieFile"):
                embed.add_field(
                    name="quality", value=movie_file["quality"]["quality"]["name"], inline=False
                )

            if size := detail.get("sizeOnDisk"):
                embed.add_field(name="size", value=f"{size / 1024**3:.2f} GB", inline=False)
        elif state is MediaState.ABSENT:
            embed.set_footer(text=f"react {REQUEST_EMOJI} to request this movie")

        return embed

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
