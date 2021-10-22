from asyncio import sleep
import logging
import logging.handlers
import multiprocessing
import re
from typing import Tuple

import discord
from discord.ext import commands
import yaml

from radarr import Radarr, Movie
import push


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

logger = logging.getLogger('wi1-bot.bot')
logger.setLevel(logging.DEBUG)

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])

bot = commands.Bot(intents=discord.Intents.all(), command_prefix=['!', '.'])


async def reply(ctx, msg: str, title: str = None, error: bool = False) -> None:
    if title is None:
        title = ''

    if len(msg) > 2048:
        msg = msg[:2045] + '...'

    embed = discord.Embed(title=title, description=msg,
                          color=discord.Color.red() if error else discord.Color.blue())

    await ctx.reply(embed=embed)


async def select_movies(ctx, command: str, movies: list[Movie]) -> Tuple[commands.Context, list[Movie]]:
    movie_list = [f'{i+1}. {movie}' for i, movie in enumerate(movies)]

    await reply(ctx, '\n'.join(movie_list), title='type in the number of the movie (or multiple separated by commas), or type c to cancel')

    def check(resp: discord.Message):
        if resp.author != ctx.message.author or resp.channel != ctx.channel:
            return False

        regex = re.compile(r'^(c|(\d+,?)+)$', re.IGNORECASE)

        if re.match(regex, resp.content.strip()):
            return True

        return False

    resp = None

    try:
        resp = await bot.wait_for('message', check=check, timeout=30)
    except Exception:
        await reply(ctx, f'timed out, {command} cancelled', error=True)
        return commands.Context(), []

    if resp.content.strip().lower() == 'c':
        await reply(resp, f'{command} cancelled')
        return resp, []

    idxs = [int(i) for i in resp.content.strip().split(',') if i.isdigit()]

    for idx in idxs:
        if idx < 1 or idx > len(movies):
            await reply(resp, f'invalid index ({idx}), {command} cancelled', error=True)
            return resp, []

    selected = []

    for idx in idxs:
        selected.append(movies[idx - 1])

    return resp, selected


@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=config['discord']['bot_presence']))
    except:
        pass

    logger.debug('bot is ready')


@bot.command(name='addmovie', help='add a movie to the plex')
async def addmovie_cmd(ctx, *args: str):
    if ctx.channel.id != config['discord']['channel_id']:
        return

    if not args:
        await reply(ctx, 'usage: !addmovie KEYWORDS...')
        return

    logger.debug(f'got !addmovie command from user {ctx.message.author.name}: {ctx.message.content}')

    async with ctx.typing():
        query = ' '.join(args)

        movies = radarr.lookup_movie(query)

        if not movies:
            await reply(ctx, f'could not find a movie matching the query: {query}', error=True)
            return

    resp, to_add = await select_movies(ctx, 'addmovie', movies)

    if not to_add:
        return

    for movie in to_add:
        if not radarr.add_movie(movie):
            await reply(resp, f'{movie} is already on the plex (idiot)')
            continue

        logger.info(f'{ctx.message.author.name} has added the movie {movie.full_title} to the plex')

        push.send(
            f'{ctx.message.author.name} has added the movie {movie.full_title}', url=movie.url)

        await reply(resp, f'added movie {movie} to the plex')

        await sleep(5)

        if not radarr.add_tag(movie, ctx.message.author._user.id):
            push.send(f'get {ctx.message.author.name} a tag', title='tag needed', priority=1)

            await ctx.send(f"hey <@!{config['discord']['admin_id']}> get this guy a tag")


@bot.command(name='delmovie', help='delete a movie from the plex')
async def delmovie_cmd(ctx, *args: str):
    if ctx.channel.id != config['discord']['channel_id']:
        return

    if not args:
        await reply(ctx, 'usage: !delmovie KEYWORDS...')
        return

    logger.debug(f'got !delmovie command from user {ctx.message.author.name}: {ctx.message.content}')

    query = ' '.join(args)

    async with ctx.typing():
        if 'plex-admin' in [role.name for role in ctx.message.author.roles]:
            movies = radarr.lookup_library(query)[:50]
        else:
            movies = radarr.lookup_user_movies(query, ctx.message.author._user.id)[:50]

        if not movies:
            if 'plex-admin' in [role.name for role in ctx.message.author.roles]:
                await reply(ctx, f'could not find a movie matching the query: {query}', error=True)
            else:
                await reply(ctx, f"you haven't added a movie matching the query: {query}", error=True)

            return

    resp, to_delete = await select_movies(ctx, 'delmovie', movies)

    if not to_delete:
        return

    for movie in to_delete:
        radarr.del_movie(movie)

        logger.info(f'{ctx.message.author.name} has deleted the movie {movie.full_title} from the plex')

        push.send(f'{ctx.message.author.name} has deleted the movie {movie.full_title}', url=movie.url)

        await reply(resp, f'deleted movie {movie} from the plex')


@commands.cooldown(1, 10)  # one time every 10 seconds
@bot.command(name='downloads', aliases=['queue', 'q'], help='see the status of movie downloads')
async def downloads_cmd(ctx):
    if ctx.channel.id != config['discord']['channel_id']:
        return

    async with ctx.typing():
        queue = radarr.get_downloads()

    if not queue:
        await reply(ctx, 'there are no pending downloads')
        return

    await reply(ctx, '\n\n'.join(map(str, queue)), title='download progress')


@commands.cooldown(1, 60)
@bot.command(name='searchmissing', help='search for missing movies that have been added')
async def searchmissing_cmd(ctx):
    if ctx.channel.id != config['discord']['channel_id']:
        return

    if 'plex-admin' not in [role.name for role in ctx.message.author.roles]:
        await reply(ctx, f'user {ctx.message.author.name} does not have permission to use this command', error=True)
        return

    radarr.search_missing()

    await reply(ctx, 'searching for missing movies...')


@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name='quota', help='see your used space on the plex')
async def quota_cmd(ctx):
    if ctx.channel.id != config['discord']['channel_id']:
        return

    async with ctx.typing():
        used = radarr.get_quota_amount(ctx.message.author._user.id) / 1024**3

        maximum = 0

        try:
            maximum = config['discord']['quotas'][ctx.message.author._user.id]
        except Exception:
            pass

        pct = used / maximum * 100 if maximum != 0 else 100

        msg = f'you have added {used:.2f}/{maximum:.2f} GB ({pct:.1f}%) of useless crap to the plex'

    await reply(ctx, msg)


@commands.cooldown(1, 60)
@bot.command(name='quotas', help="see everyone's used space on the plex")
async def quotas_cmd(ctx):
    if ctx.channel.id != config['discord']['channel_id']:
        return

    quotas = config['discord']['quotas']

    if not quotas:
        await reply(ctx, 'quotas are not implemented here')

    async with ctx.typing():
        msg = []

        for user_id, total in quotas.items():
            used = radarr.get_quota_amount(user_id) / 1024**3

            pct = used / total * 100 if total != 0 else 100

            user = await bot.fetch_user(user_id)

            msg.append(f'{user.display_name}: {used:.2f}/{total:.2f} GB ({pct:.1f}%)')

    await reply(ctx, '\n'.join(sorted(msg)), title='quotas of users who have bought space')


def run(logging_queue: multiprocessing.Queue) -> None:
    queue_handler = logging.handlers.QueueHandler(logging_queue)

    logger.addHandler(queue_handler)

    logger.debug('starting bot')

    bot.run(config['discord']['bot_token'])


if __name__ == '__main__':
    logger.addHandler(logging.StreamHandler())
    bot.run(config['discord']['bot_token'])
