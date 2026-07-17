import asyncio
import logging

import discord
import requests
from discord.ext import commands

from wi1_bot.arr import MediaState
from wi1_bot.arr.sonarr import Series, Sonarr, SonarrError
from wi1_bot.bot.config import config
from wi1_bot.bot.tmdb import SeriesDetails, Tmdb
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


class SeriesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.sonarr = Sonarr.from_config(config.sonarr)
        self.tmdb = Tmdb.from_config(config.tmdb)

    @commands.command(name="addshow", help="add a show to the plex")
    @commands.has_any_role("plex-admin", "plex-shows")
    async def addshow_cmd(self, ctx: commands.Context[commands.Bot], *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !addshow KEYWORDS...")
            return

        async with ctx.typing():
            try:
                potential = self.sonarr.lookup_series(query)
            except SonarrError as e:
                await reply(
                    ctx.message,
                    (f"there was an error that isn't <@!{config.discord.admin_id}>'s fault: {e}"),
                    error=True,
                )
                return

            if not potential:
                await reply(
                    ctx.message,
                    f"could not find a show matching the query: {query}",
                    error=True,
                )
                return

            # resolve each result's state up front so the picker can show what's already
            # on plex / monitored before the user commits to adding it
            states = {series: self.sonarr.series_state(series) for series in potential}

        try:
            to_add, resp = await select_from_list(
                self.bot,
                ctx.message,
                potential,
                render=lambda series: f"{series}{STATE_SUFFIX[states[series]]}",
            )
        except SelectTimeout:
            await reply(ctx.message, "timed out, addshow cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "addshow cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), addshow cancelled", error=True)
            return

        if not to_add:
            return

        await self._add_series(resp, to_add, ctx.message.author)

    async def _add_series(
        self,
        resp: discord.Message,
        to_add: list[Series],
        requester: discord.Member | discord.User,
        announce_requester: bool = False,
    ) -> None:
        added: list[Series] = []

        for series in to_add:
            if not self.sonarr.add_series(series):
                if self.sonarr.series_downloaded(series):
                    await reply(resp, f"{series} is already DOWNLOADED on the plex (idiot)")
                else:
                    await reply(resp, f"{series} is already on the plex (idiot)")
                continue

            self.logger.info(f"{requester.name} has added the show {series.full_title}")

            push.send(
                config.pushover,
                f"{requester.name} has added the show {series.full_title}",
                url=series.url,
            )

            msg = f"added show {series} to the plex"

            if announce_requester:
                msg += f" (requested by {requester.display_name})"

            await reply(resp, msg)

            added.append(series)

        if not added:
            return

        await asyncio.sleep(10)

        for series in added:
            if not self.sonarr.add_tag(series, requester.id):
                push.send(
                    config.pushover,
                    f"get {requester.name} a tag",
                    title="tag needed",
                    priority=1,
                )

                await resp.channel.send(f"hey <@!{config.discord.admin_id}> get this guy a tag")

                return

    @commands.command(name="showinfo", help="get information about a show")
    async def showinfo_cmd(self, ctx: commands.Context[commands.Bot], *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !showinfo KEYWORDS...")
            return

        async with ctx.typing():
            try:
                potential = self.sonarr.lookup_series(query)
            except SonarrError as e:
                await reply(
                    ctx.message,
                    (f"there was an error that isn't <@!{config.discord.admin_id}>'s fault: {e}"),
                    error=True,
                )
                return

            if not potential:
                await reply(
                    ctx.message,
                    f"could not find a show matching the query: {query}",
                    error=True,
                )
                return

            # resolve each result's state up front so the picker can show what's already
            # on plex / monitored before the user commits to selecting it
            states = {series: self.sonarr.series_state(series) for series in potential}

        try:
            selected, resp = await select_from_list(
                self.bot,
                ctx.message,
                potential,
                render=lambda series: f"{series}{STATE_SUFFIX[states[series]]}",
            )
        except SelectTimeout:
            await reply(ctx.message, "timed out, showinfo cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "showinfo cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), showinfo cancelled", error=True)
            return

        if not selected:
            return

        offers: list[asyncio.Task[None]] = []

        for series in selected:
            async with ctx.typing():
                state = states[series]
                embed = self._build_series_embed(series, state)

            info_msg = await resp.reply(embed=embed)

            if state is MediaState.ABSENT:
                # each offer waits for a request reaction; run them as tasks so
                # multiple selections don't wait serially
                offers.append(asyncio.create_task(self._offer_series_request(info_msg, series)))

        if offers:
            await asyncio.gather(*offers)

    async def _offer_series_request(self, info_msg: discord.Message, series: Series) -> None:
        user = await wait_for_request_reaction(self.bot, info_msg)

        if user is None:
            return

        # !addshow is role-gated, so the reaction shortcut has to be too
        if not (
            await member_has_role(user, "plex-admin") or await member_has_role(user, "plex-shows")
        ):
            await reply(
                info_msg,
                f"{user.display_name}, you don't have permission to do that",
                error=True,
            )
            return

        self.logger.info(f"{user.name} requested the show {series.full_title} via reaction")

        await self._add_series(info_msg, [series], user, announce_requester=True)

    def _series_details(self, series: Series) -> SeriesDetails | None:
        if self.tmdb is None:
            return None

        try:
            return self.tmdb.series_details(series.tvdb_id)
        except requests.RequestException:
            self.logger.warning(
                f"failed to fetch tmdb details for {series.full_title}", exc_info=True
            )
            return None

    def _build_series_embed(self, series: Series, state: MediaState) -> discord.Embed:
        json = series.json

        overview: str = json.get("overview", "")

        embed = discord.Embed(
            title=series.full_title,
            url=series.url,
            description=overview[:1024],
            color=discord.Color.blue(),
        )

        if poster := json.get("remotePoster"):
            embed.set_thumbnail(url=poster)

        if airing := json.get("status"):
            embed.add_field(name="airing", value=airing, inline=False)

        if network := json.get("network"):
            embed.add_field(name="network", value=network, inline=False)

        if runtime := json.get("runtime"):
            embed.add_field(
                name="runtime", value=f"{format_runtime(runtime)}/episode", inline=False
            )

        if genres := json.get("genres"):
            embed.add_field(name="genres", value=", ".join(genres), inline=False)

        if certification := json.get("certification"):
            embed.add_field(name="rated", value=certification, inline=False)

        seasons = [s for s in json.get("seasons", []) if s.get("seasonNumber", 0) > 0]

        if seasons:
            embed.add_field(name="seasons", value=str(len(seasons)), inline=False)

        details = self._series_details(series)

        rating_parts: list[str] = []

        # unrated shows report no value (or 0)
        if value := (json.get("ratings") or {}).get("value"):
            rating_parts.append(f"tvdb {value:.1f}/10")

        if details is not None and details.rating:
            rating_parts.append(f"tmdb {details.rating:.1f}/10")

        embed.add_field(
            name="ratings",
            value=" | ".join(rating_parts) if rating_parts else "unrated",
            inline=False,
        )

        if details is not None:
            if details.credits.directors:
                embed.add_field(
                    name="created by",
                    value=", ".join(map(str, details.credits.directors)),
                    inline=False,
                )
            if details.credits.cast:
                embed.add_field(
                    name="cast", value=", ".join(map(str, details.credits.cast)), inline=False
                )

        embed.add_field(name="status", value=STATE_LABEL[state], inline=False)

        if state is MediaState.DOWNLOADED:
            assert series.db_id is not None
            detail = self.sonarr.get_series_by_id(series.db_id)

            stats = detail.get("statistics") or {}

            if episode_count := stats.get("episodeCount"):
                embed.add_field(
                    name="episodes",
                    value=f"{stats.get('episodeFileCount', 0)}/{episode_count} downloaded",
                    inline=False,
                )

            if size := stats.get("sizeOnDisk"):
                embed.add_field(name="size", value=f"{size / 1024**3:.2f} GB", inline=False)
        elif state is MediaState.ABSENT:
            embed.set_footer(text=f"react {REQUEST_EMOJI} to request this show")

        return embed

    @commands.command(name="delshow", help="delete a show from the plex")
    @commands.has_any_role("plex-admin", "plex-shows")
    async def delshow_command(
        self, ctx: commands.Context[commands.Bot], *, query: str = ""
    ) -> None:
        if not query:
            await reply(ctx.message, "usage: !delshow KEYWORDS...")
            return

        async with ctx.typing():
            if await member_has_role(ctx.message.author, "plex-admin"):
                potential = self.sonarr.lookup_library(query)[:50]

                if not potential:
                    await reply(
                        ctx.message,
                        f"could not find a show matching the query: {query}",
                        error=True,
                    )
                    return
            else:
                potential = self.sonarr.lookup_user_library(query, ctx.message.author.id)[:50]

                if not potential:
                    await reply(
                        ctx.message,
                        f"you haven't added a show matching the query: {query}",
                        error=True,
                    )
                    return

        try:
            to_delete, resp = await select_from_list(self.bot, ctx.message, potential)
        except SelectTimeout:
            await reply(ctx.message, "timed out, delshow cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "delshow cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), delshow cancelled", error=True)
            return

        if not to_delete:
            return

        for series in to_delete:
            self.sonarr.del_series(series)

            self.logger.info(f"{ctx.message.author.name} has deleted the show {series.full_title}")

            push.send(
                config.pushover,
                f"{ctx.message.author.name} has deleted the show {series.full_title}",
                url=series.url,
            )

            await reply(resp, f"deleted show {series} from the plex")
