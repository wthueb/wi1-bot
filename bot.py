from asyncio import sleep
import logging
from logging.handlers import RotatingFileHandler
from multiprocessing import Process
import re

import discord
from discord.ext import commands
import yaml

import arr_webhook
from radarr import Radarr
import push


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s')

stream_handler = logging.StreamHandler()
file_handler = RotatingFileHandler('logs/wi1-bot.log', maxBytes=1024**2 * 10, backupCount=10)

stream_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(stream_handler)

logger = logging.getLogger('wi1-bot')
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])

bot = commands.Bot(intents=discord.Intents.all(), command_prefix=['!', '.'])


async def reply(replyto, msg: str, title: str = None, error: bool = False) -> None:
    if title is None:
        title = ''

    embed = discord.Embed(title=title, description=msg,
                          color=discord.Color.red() if error else discord.Color.blue())

    await replyto.reply(embed=embed)


@bot.event
async def on_ready():
    try:
        await bot.change_presence(activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=config['discord']['bot_presence']))
    except:
        pass


@bot.command(name='addmovie', help='add a movie to the plex')
async def addmovie_cmd(ctx, *args):
    if ctx.message.channel.id != config['discord']['channel_id']:
        return

    if not args:
        await reply(ctx, 'usage: !addmovie KEYWORDS...')
        return

    logger.info(f'got !addmovie command from user {ctx.message.author.name}: {ctx.message.content}')

    async with ctx.typing():
        query = ' '.join(args)

        possible = radarr.lookup_movie(query)

        if not possible:
            await reply(ctx, f'could not find the movie with the query: {query}', error=True)
            return

        movie_list = [f'{i+1}. {movie}' for i, movie in enumerate(possible)]

    await reply(ctx, '\n'.join(movie_list), title='type in the number of the movie to add (or multiple separated by commas), or type c to cancel')

    def check(resp: discord.Message):
        if resp.author != ctx.message.author or resp.channel != ctx.message.channel:
            return False

        regex = re.compile(r'^(c|(\d+,?)+)$')

        if re.match(regex, resp.content.strip()):
            return True

        return False

    resp = None

    try:
        resp = await bot.wait_for('message', check=check, timeout=30)
    except Exception:
        await reply(ctx, 'timed out, add movie cancelled', error=True)
        return

    if resp.content.strip().lower() == 'c':
        await reply(resp, 'add movie cancelled')
        return

    idxs = [int(i) - 1 for i in resp.content.strip().split(',') if i.isdigit()]

    for idx in idxs:
        if idx < 0 or idx >= len(possible):
            await reply(resp, f'invalid index ({idx + 1}), add movie cancelled', error=True)
            return

    for idx in idxs:
        movie = possible[idx]

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

            await ctx.send(f'hey <@!{config["discord"]["admin_id"]}> get this guy a tag')


@bot.command(name='delmovie', help='delete a movie from the plex')
async def delmovie_cmd(ctx, *args):
    if ctx.message.channel.id != config['discord']['channel_id']:
        return

    if 'plex-admin' not in [role.name for role in ctx.message.author.roles]:
        await reply(ctx, f'user {ctx.message.author.name} does not have permission to use this command', error=True)
        return

    if not args:
        await reply(ctx, 'usage: !delmovie KEYWORDS...')
        return

    logger.info(f'got !delmovie command from user {ctx.message.author.name}: {ctx.message.content}')

    query = ' '.join(args)

    possible = radarr.lookup_library(query)

    if not possible:
        await reply(ctx, f'could not find the movie with the query: {query}', error=True)
        return

    movie_list = [f'{i+1}. {movie}' for i, movie in enumerate(possible)]

    await reply(ctx, '\n'.join(movie_list), title='type in the number of the movie to delete (or multiple separated by commas), or type c to cancel')

    def check(resp: discord.Message):
        if resp.author != ctx.message.author or resp.channel != ctx.message.channel:
            return False

        regex = re.compile(r'^(c|(\d+,?)+)$')

        if re.match(regex, resp.content.strip()):
            return True

        return False

    resp = None

    try:
        resp = await bot.wait_for('message', check=check, timeout=30)
    except Exception:
        await reply(ctx, 'timed out, del movie cancelled', error=True)
        return

    if resp.content.strip().lower() == 'c':
        await reply(resp, 'del movie cancelled')
        return

    idxs = [int(i) - 1 for i in resp.content.strip().split(',') if i.isdigit()]

    for idx in idxs:
        if idx < 0 or idx >= len(possible):
            await reply(resp, f'invalid index ({idx + 1}), del movie cancelled', error=True)
            return

    for idx in idxs:
        movie = possible[idx]

        radarr.del_movie(movie)

        logger.info(f'{ctx.message.author.name} has deleted the movie {movie.full_title} from the plex')

        push.send(f'{ctx.message.author.name} has deleted the movie {movie.full_title}', url=movie.url)

        await reply(resp, f'deleted movie {movie} from the plex')


@commands.cooldown(1, 10)  # one time every 10 seconds
@bot.command(name='downloads', help='see the status of movie downloads')
async def downloads_cmd(ctx):
    if ctx.message.channel.id != config['discord']['channel_id']:
        return

    async with ctx.typing():
        queue = radarr.get_downloads()

    if not queue:
        await reply(ctx, 'there are no pending downloads')

    await reply(ctx, '\n\n'.join(map(str, queue)), title='download progress')


@commands.cooldown(1, 60)
@bot.command(name='searchmissing', help='search for missing movies that have been added')
async def searchmissing_cmd(ctx):
    if ctx.message.channel.id != config['discord']['channel_id']:
        return

    if 'plex-admin' not in [role.name for role in ctx.message.author.roles]:
        await reply(ctx, f'user {ctx.message.author.name} does not have permission to use this command', error=True)
        return

    radarr.search_missing()

    await reply(ctx, 'searching for missing movies...')


@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name='quota', help='see your used space on the plex')
async def quota_cmd(ctx):
    if ctx.message.channel.id != config['discord']['channel_id']:
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
    if ctx.message.channel.id != config['discord']['channel_id']:
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


if __name__ == '__main__':
    logger.info('starting webhook listener')

    wh = Process(target=arr_webhook.run)
    wh.daemon = True
    wh.start()

    logger.info('started webhook listener, starting bot')

    bot.run(config['discord']['bot_token'])
