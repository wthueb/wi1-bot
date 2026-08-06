import asyncio
from collections import defaultdict

import discord
import structlog
from discord.ext import commands, tasks

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.arr.episode import Episode
from wi1_bot.arr.radarr import Movie
from wi1_bot.arr.sonarr import Series, SonarrError
from wi1_bot.bot.config import config
from wi1_bot.bot.models import NotifyMethod, RequestKind
from wi1_bot.bot.notifications import (
    ActiveRequest,
    active_requests,
    mark_episodes_seen,
    mark_notified,
    prune_seen_episodes,
    record_request,
    remove_request,
    requests_for_user,
    seen_episode_ids,
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
        # a bare !notify shows what the user is already waiting on; listing works even
        # when polling is off, so it runs before the disabled check
        if not query:
            await self._show_subscriptions(ctx)
            return

        if not config.notifications.enabled:
            # nothing polls *arr when disabled, so a subscription would never fire
            await reply(ctx.message, "notifications are disabled on this bot", error=True)
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

    @commands.command(
        name="subscriptions",
        aliases=["subs"],
        help="see what you're waiting on notifications for",
    )
    async def subscriptions_cmd(self, ctx: commands.Context[commands.Bot]) -> None:
        await self._show_subscriptions(ctx)

    async def _show_subscriptions(self, ctx: commands.Context[commands.Bot]) -> None:
        subs = await asyncio.to_thread(requests_for_user, ctx.author.id)

        if not subs:
            await reply(ctx.message, "you aren't waiting on anything", title="your notifications")
            return

        lines: list[str] = []

        if not config.notifications.enabled:
            lines.append("**notifications are disabled on this bot — nothing will be sent**\n")

        movies = [sub for sub in subs if sub.kind == RequestKind.MOVIE]
        if movies:
            lines.append("**movies**")
            lines.extend(f"- {sub.title}" for sub in movies)

        shows = [sub for sub in subs if sub.kind == RequestKind.SERIES]
        if shows:
            if movies:
                lines.append("")
            lines.append("**shows**")
            lines.extend(f"- {sub.title}" for sub in shows)

        await reply(ctx.message, "\n".join(lines), title="your notifications")

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
        active = await asyncio.to_thread(active_requests)

        subscribed_tvdb_ids = {
            req.tvdb_id
            for req in active
            if req.kind == RequestKind.SERIES and req.tvdb_id is not None
        }
        await asyncio.to_thread(prune_seen_episodes, subscribed_tvdb_ids)

        if not active:
            return

        # one library fetch per instance covers every active request; likewise fetch
        # each subscriber's delivery preference once instead of per-notification
        movie_ids, episodes_by_tvdb, methods = await asyncio.gather(
            asyncio.to_thread(self.radarr.downloaded_movie_tmdb_ids),
            asyncio.to_thread(self.sonarr.downloaded_episodes_by_tvdb_id, subscribed_tvdb_ids),
            asyncio.to_thread(get_notify_methods, [req.discord_id for req in active]),
        )

        notified: list[int] = []

        for req in active:
            if req.kind != RequestKind.MOVIE or req.tmdb_id not in movie_ids:
                continue

            method = methods.get(req.discord_id, DEFAULT_NOTIFY_METHOD)
            if await self._notify(req, f"**{req.title}** is now on plex!", method):
                notified.append(req.id)

        by_tvdb: dict[int, list[ActiveRequest]] = defaultdict(list)
        for req in active:
            if req.kind == RequestKind.SERIES and req.tvdb_id is not None:
                by_tvdb[req.tvdb_id].append(req)

        for tvdb_id, reqs in by_tvdb.items():
            episodes = episodes_by_tvdb.get(tvdb_id)
            if episodes is None:
                # the show is gone from sonarr; keep the subscription in case it returns
                continue

            notified.extend(await self._reconcile_series(tvdb_id, reqs, episodes, methods))

        if notified:
            await asyncio.to_thread(mark_notified, notified)

    async def _reconcile_series(
        self,
        tvdb_id: int,
        reqs: list[ActiveRequest],
        episodes: list[Episode],
        methods: dict[int, NotifyMethod],
    ) -> list[int]:
        seen = await asyncio.to_thread(seen_episode_ids, tvdb_id)
        new = [ep for ep in episodes if ep.db_id is not None and ep.db_id not in seen]

        notified: list[int] = []

        if episodes:
            count = len(episodes)
            for req in (r for r in reqs if not r.notified):
                message = (
                    f"There {'are' if count > 1 else 'is'} {count}"
                    f" episode{'s' if count > 1 else ''} of **{req.title}** already on plex!"
                )
                method = methods.get(req.discord_id, DEFAULT_NOTIFY_METHOD)
                if await self._notify(req, message, method):
                    notified.append(req.id)

        if new and seen:
            newest = max(new, key=lambda ep: (ep.season_num, ep.ep_num))
            extra = len(new) - 1
            message = f"**{newest.full_title}** is now on plex!"
            if extra:
                message += f" (+{extra} more episode{'s' if extra > 1 else ''})"

            for req in (r for r in reqs if r.notified):
                method = methods.get(req.discord_id, DEFAULT_NOTIFY_METHOD)
                await self._notify(req, message, method)

        if new:
            await asyncio.to_thread(
                mark_episodes_seen, tvdb_id, [ep.db_id for ep in new if ep.db_id is not None]
            )

        return notified

    async def _notify(
        self, req: ActiveRequest, message: str, method: NotifyMethod = DEFAULT_NOTIFY_METHOD
    ) -> bool:
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

    async def _notify_in_channel(self, req: ActiveRequest, message: str) -> bool:
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
