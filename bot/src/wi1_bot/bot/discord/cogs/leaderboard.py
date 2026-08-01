import asyncio
from datetime import datetime

import discord
import structlog
from discord.ext import commands, tasks

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.bot.config import config
from wi1_bot.bot.leaderboard import LeaderboardRow, get_leaderboard, refresh_leaderboard
from wi1_bot.bot.models import utcnow

from ..helpers import reply


def _updated_ago(updated_at: datetime) -> str:
    seconds = (utcnow() - updated_at).total_seconds()
    if seconds < 90:
        return "just now"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"{minutes}m ago"
    return f"{round(minutes / 60)}h ago"


class LeaderboardCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.logger = structlog.get_logger(__name__)
        self.radarr = Radarr.from_config(config.radarr)
        self.sonarr = Sonarr.from_config(config.sonarr)

    async def cog_load(self) -> None:
        self.refresh_loop.change_interval(minutes=config.leaderboard.refresh_interval)
        self.refresh_loop.start()

    async def cog_unload(self) -> None:
        self.refresh_loop.cancel()

    @tasks.loop(minutes=15)  # overridden from config in cog_load
    async def refresh_loop(self) -> None:
        # blocking *arr calls + DB writes go off the event loop; a transient *arr error
        # must not kill the loop, so swallow-and-log and try again next interval
        try:
            await asyncio.to_thread(refresh_leaderboard, self.radarr, self.sonarr)
        except Exception:
            self.logger.exception("failed to refresh leaderboard cache")

    @refresh_loop.before_loop
    async def _before_refresh(self) -> None:
        await self.bot.wait_until_ready()

    @commands.command(
        name="leaderboard", aliases=["lb", "top"], help="see who has added the most titles"
    )
    async def leaderboard_cmd(self, ctx: commands.Context[commands.Bot]) -> None:
        rows, updated_at = await asyncio.to_thread(get_leaderboard)

        if not rows:
            await reply(ctx.message, "no titles have been attributed to anyone yet")
            return

        # resolve display names (cache first, then a fetch) and finalize the ordering
        resolved: list[tuple[LeaderboardRow, str]] = []
        for row in rows:
            user = self.bot.get_user(row.discord_id)
            if user is None:
                try:
                    user = await self.bot.fetch_user(row.discord_id)
                except discord.NotFound:
                    continue
            resolved.append((row, user.display_name))

        resolved.sort(key=lambda r: (-r[0].total, r[1].lower()))

        lines = [
            f"{i + 1}. **{name}** — {row.total}"
            f" ({row.movie_count} movies, {row.series_count} shows)"
            for i, (row, name) in enumerate(resolved)
        ]

        if updated_at is not None:
            lines.append(f"\n*updated {_updated_ago(updated_at)}*")

        await reply(ctx.message, "\n".join(lines), title="leaderboard")
