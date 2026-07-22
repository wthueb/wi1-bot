import discord
from discord.ext import commands

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.bot.config import config

from ..helpers import parse_user_tag, reply


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.radarr = Radarr.from_config(config.radarr)
        self.sonarr = Sonarr.from_config(config.sonarr)

    @commands.command(name="addtag", help="add a user tag")
    @commands.has_role("plex-admin")
    async def addtag_cmd(
        self, ctx: commands.Context[commands.Bot], name: str, user: discord.Member
    ) -> None:
        tag = f"{name}-{user.id}"

        self.radarr.create_tag(tag)
        self.sonarr.create_tag(tag)

        await reply(ctx.message, f"tag `{tag}` added for {user.display_name}")

    @commands.command(name="showtags", help="see who has been assigned a tag")
    @commands.has_role("plex-admin")
    async def showtags_cmd(self, ctx: commands.Context[commands.Bot]) -> None:
        async with ctx.typing():
            # !addtag writes to both instances, so a label missing from one side is drift
            # worth surfacing; merge them and note which instance a tag is unique to
            radarr_labels = set(self.radarr.get_tags())
            sonarr_labels = set(self.sonarr.get_tags())

            lines: list[str] = []

            for label in radarr_labels | sonarr_labels:
                parsed = parse_user_tag(label)
                if parsed is None:
                    continue

                _, user_id = parsed

                # resolve the account without pinging: a display name is plain text,
                # unlike a <@id> mention. prefer the cache, fall back to a fetch
                user = self.bot.get_user(user_id)
                if user is None:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except discord.NotFound:
                        user = None

                who = user.display_name if user is not None else "unknown user"

                drift = ""
                if label not in radarr_labels:
                    drift = " *(sonarr only)*"
                elif label not in sonarr_labels:
                    drift = " *(radarr only)*"

                lines.append(f"`{label}` — {who}{drift}")

        if not lines:
            await reply(ctx.message, "no user tags have been assigned yet")
            return

        await reply(ctx.message, "\n".join(sorted(lines)), title="assigned tags")
