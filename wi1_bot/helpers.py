import discord


async def member_has_role(member: discord.Member | discord.User, role: str) -> bool:
    if isinstance(member, discord.Member):
        return role in [r.name for r in member.roles]

    return False


async def reply(
    msg: discord.Message, content: str, title: str = "", error: bool = False
) -> None:
    if len(content) > 2048:
        content = content[:2045] + "..."

    embed = discord.Embed(
        title=title,
        description=content,
        color=discord.Color.red() if error else discord.Color.blue(),
    )

    await msg.reply(embed=embed)
