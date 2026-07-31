import asyncio

import discord
import structlog
from discord.ext import commands, tasks

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.arr.radarr import Movie
from wi1_bot.arr.sonarr import Series, SonarrError
from wi1_bot.bot.config import config
from wi1_bot.bot.models import NotifyMethod, RequestKind
from wi1_bot.bot.notifications import (
    PendingRequest,
    mark_notified,
    pending_requests,
    record_request,
    remove_request,
)
from wi1_bot.bot.settings import DEFAULT_NOTIFY_METHOD, get_notify_methods

from ..helpers import (
    NOTIFY_EMOJI,
    UNNOTIFY_EMOJI,
    SelectCancelled,
    SelectInvalidIndex,
    SelectTimeout,
    collect_reaction_choices,
    reply,
    select_from_list,
)

logger = structlog.get_logger(__name__)


class NotifyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.radarr = Radarr.from_config(config.radarr)
        self.sonarr = Sonarr.from_config(config.sonarr)
        self._tasks: set[asyncio.Task[None]] = set()

    async def cog_load(self) -> None:
        if config.notifications.enabled:
            self.poll_loop.change_interval(seconds=config.notifications.poll_interval)
            self.poll_loop.start()

    async def cog_unload(self) -> None:
        if self.poll_loop.is_running():
            self.poll_loop.cancel()

    @commands.command(
        name="notify", help="get notified (or stop) when titles on the plex finish downloading"
    )
    async def notify_cmd(self, ctx: commands.Context[commands.Bot], *, query: str = "") -> None:
        if not config.notifications.enabled:
            # nothing polls *arr when disabled, so a subscription would never fire
            await reply(ctx.message, "notifications are disabled on this bot", error=True)
            return

        if not query:
            await reply(ctx.message, "usage: !notify KEYWORDS...")
            return

        async with ctx.typing():
            try:
                # only library titles can be waited on; combine movies + shows into one list
                results: list[Movie | Series] = [
                    *self.radarr.lookup_library(query)[:25],
                    *self.sonarr.lookup_library(query)[:25],
                ]
            except SonarrError as e:
                await reply(
                    ctx.message,
                    f"there was an error that isn't <@!{config.discord.admin_id}>'s fault: {e}",
                    error=True,
                )
                return

            if not results:
                await reply(ctx.message, f"nothing on the plex matches: {query}", error=True)
                return

        try:
            selected, resp = await select_from_list(
                self.bot,
                ctx.message,
                results,
                render=lambda item: f"{item} ({'movie' if isinstance(item, Movie) else 'show'})",
            )
        except SelectTimeout:
            await reply(ctx.message, "timed out, notify cancelled", error=True)
            return
        except SelectCancelled as e:
            await reply(e.resp, "notify cancelled")
            return
        except SelectInvalidIndex as e:
            await reply(e.resp, f"invalid index ({e.index}), notify cancelled", error=True)
            return

        if not selected:
            return

        titles = "\n".join(f"- {item}" for item in selected)
        prompt = await reply(
            resp,
            f"{titles}\n\nreact with the bell to be notified on completion,"
            " or the crossed-out bell to stop",
            title="notifications",
        )

        async def subscribe(user: discord.Member | discord.User) -> None:
            for item in selected:
                await asyncio.to_thread(self._record_item, user, item, prompt.channel.id)
            logger.info("user subscribed", user=user.name, titles=len(selected))

        async def unsubscribe(user: discord.Member | discord.User) -> None:
            for item in selected:
                await asyncio.to_thread(self._remove_item, user, item)
            logger.info("user unsubscribed", user=user.name, titles=len(selected))

        task = asyncio.create_task(
            collect_reaction_choices(
                self.bot, prompt, {NOTIFY_EMOJI: subscribe, UNNOTIFY_EMOJI: unsubscribe}
            )
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    def _record_item(
        self, user: discord.Member | discord.User, item: Movie | Series, channel_id: int
    ) -> None:
        if isinstance(item, Movie):
            record_request(
                discord_id=user.id,
                kind=RequestKind.MOVIE,
                tmdb_id=item.tmdb_id,
                title=item.full_title,
                channel_id=channel_id,
            )
        else:
            record_request(
                discord_id=user.id,
                kind=RequestKind.SERIES,
                tvdb_id=item.tvdb_id,
                title=item.full_title,
                channel_id=channel_id,
            )

    def _remove_item(self, user: discord.Member | discord.User, item: Movie | Series) -> None:
        if isinstance(item, Movie):
            remove_request(discord_id=user.id, kind=RequestKind.MOVIE, tmdb_id=item.tmdb_id)
        else:
            remove_request(discord_id=user.id, kind=RequestKind.SERIES, tvdb_id=item.tvdb_id)

    @tasks.loop(seconds=60)  # interval is overridden from config in cog_load
    async def poll_loop(self) -> None:
        # one bad *arr response must not kill the loop; log and retry next interval
        try:
            await self._reconcile()
        except Exception:
            logger.exception("notification poll failed")

    @poll_loop.before_loop
    async def _before_poll(self) -> None:
        await self.bot.wait_until_ready()

    async def _reconcile(self) -> None:
        pending = await asyncio.to_thread(pending_requests)
        if not pending:
            return

        # one library fetch per instance covers every pending request; likewise fetch
        # each subscriber's delivery preference once instead of per-notification
        movie_ids, series_ids, methods = await asyncio.gather(
            asyncio.to_thread(self.radarr.downloaded_movie_tmdb_ids),
            asyncio.to_thread(self.sonarr.downloaded_series_tvdb_ids),
            asyncio.to_thread(get_notify_methods, [req.discord_id for req in pending]),
        )

        notified: list[int] = []

        for req in pending:
            downloaded = (req.kind == RequestKind.MOVIE and req.tmdb_id in movie_ids) or (
                req.kind == RequestKind.SERIES and req.tvdb_id in series_ids
            )
            if not downloaded:
                continue

            method = methods.get(req.discord_id, DEFAULT_NOTIFY_METHOD)
            if await self._notify(req, method):
                notified.append(req.id)

        if notified:
            await asyncio.to_thread(mark_notified, notified)

    async def _notify(
        self, req: PendingRequest, method: NotifyMethod = DEFAULT_NOTIFY_METHOD
    ) -> bool:
        message = f"**{req.title}** is now on plex!"

        # honour the subscriber's preference; "channel" pings them in the request channel
        # rather than opening a DM
        if method == NotifyMethod.CHANNEL:
            return await self._notify_in_channel(req, message)

        user = self.bot.get_user(req.discord_id)
        if user is None:
            try:
                user = await self.bot.fetch_user(req.discord_id)
            except discord.NotFound:
                logger.warning("cannot notify unknown user", user=req.discord_id, title=req.title)
                return True

        try:
            await user.send(message)
            return True
        except discord.Forbidden:
            # the user has DMs closed; fall back to a mention in the request's channel
            return await self._notify_in_channel(req, message)
        except discord.HTTPException:
            logger.warning("failed to DM, will retry", user=req.discord_id, exc_info=True)
            return False

    async def _notify_in_channel(self, req: PendingRequest, message: str) -> bool:
        channel = self.bot.get_channel(req.channel_id)
        if not isinstance(channel, discord.abc.Messageable):
            logger.warning("no usable fallback channel", user=req.discord_id)
            return True  # nowhere to send it; don't retry forever

        try:
            await channel.send(f"<@!{req.discord_id}> {message}")
            return True
        except discord.HTTPException:
            logger.warning("failed to notify in channel, will retry", user=req.discord_id)
            return False
