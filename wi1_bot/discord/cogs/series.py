import asyncio
import logging

from discord.ext import commands

from wi1_bot import push
from wi1_bot.arr.sonarr import Series, Sonarr
from wi1_bot.config import config

from ..helpers import reply, select_from_list


class SeriesCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])

    @commands.command(name="addshow", help="add a show to the plex")
    @commands.has_role("plex-admin")
    async def addshow_cmd(self, ctx: commands.Context, *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !addshow KEYWORDS...")
            return

        async with ctx.typing():
            potential = self.sonarr.lookup_series(query)

            if not potential:
                await reply(
                    ctx.message,
                    f"could not find a show matching the query: {query}",
                    error=True,
                )
                return

        resp, to_add = await select_from_list(
            self.bot, ctx.message, "addshow", potential
        )

        if not to_add:
            return

        added: list[Series] = []

        for series in to_add:
            if not self.sonarr.add_series(series):
                if self.sonarr.series_downloaded(series):
                    await reply(
                        resp, f"{series} is already DOWNLOADED on the plex (idiot)"
                    )
                else:
                    await reply(resp, f"{series} is already on the plex (idiot)")
                continue

            self.logger.info(
                f"{ctx.message.author.name} has added the show {series.full_title}"
            )

            push.send(
                f"{ctx.message.author.name} has added the show {series.full_title}",
                url=series.url,
            )

            await reply(resp, f"added show {series} to the plex")

            added.append(series)

        if not added:
            return

        await asyncio.sleep(10)

        for series in added:
            if not self.sonarr.add_tag(series, ctx.message.author.id):
                push.send(
                    f"get {ctx.message.author.name} a tag",
                    title="tag needed",
                    priority=1,
                )

                await ctx.send(
                    f"hey <@!{config['discord']['admin_id']}> get this guy a tag"
                )

                return

    @commands.command(name="delshow", help="delete a show from the plex")
    @commands.has_role("plex-admin")
    async def delshow_command(self, ctx: commands.Context, *, query: str = "") -> None:
        if not query:
            await reply(ctx.message, "usage: !delshow KEYWORDS...")
            return

        async with ctx.typing():
            potential = self.sonarr.lookup_library(query)[:50]

            if not potential:
                await reply(
                    ctx.message,
                    f"could not find a show matching the query: {query}",
                    error=True,
                )
                return

        resp, to_delete = await select_from_list(
            self.bot, ctx.message, "delshow", potential
        )

        if not to_delete:
            return

        for series in to_delete:
            self.sonarr.del_series(series)

            self.logger.info(
                f"{ctx.message.author.name} has deleted the show {series.full_title}"
            )

            push.send(
                f"{ctx.message.author.name} has deleted the show {series.full_title}",
                url=series.url,
            )

            await reply(resp, f"deleted show {series} from the plex")
