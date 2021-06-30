import logging
from logging.handlers import RotatingFileHandler
import re

import discord
from discord.ext import commands
from discord.utils import get
from transmission_rpc import Client as TransmissionClient
from pushover import Client as PushoverClient

from radarr import Radarr

from config import *


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)

formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s')

# log to file, but everything to stdout

file_handler = RotatingFileHandler('logs/wi1-bot.log', maxBytes=1024**2 * 10, backupCount=10)
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logger.addHandler(stream_handler)
root_logger.addHandler(stream_handler)

radarr = Radarr(RADARR_URL, RADARR_API_KEY)

pushover = PushoverClient(PUSHOVER_USER_KEY, api_token=PUSHOVER_API_KEY)

bot = commands.Bot(intents=discord.Intents.all(), command_prefix=['!', '.'])


def send_push(msg: str, priority=0):
    pushover.send_message(msg, priority=priority, device=PUSHOVER_DEVICES)


def movie_text(movie: dict):
    return f'[{movie["title"]} ({movie["year"]})](https://www.themoviedb.org/movie/{movie["tmdbId"]})'


async def reply(replyto, msg: str, title: str = None, error: bool = False):
    if title is None:
        title = ''

    embed = discord.Embed(title=title, description=msg,
                          color=discord.Color.red() if error else discord.Color.blue())

    await replyto.reply(embed=embed)


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="david cronenberg's 1996 pièce de résistance, crash"))


@bot.event
async def on_member_join(member: discord.Member):
    try:
        if USER_IDS[member._user.id] in ['shep', 'ethan']:
            role = get(member.guild.roles, name='5v5')

            await member.add_roles(role)
    except Exception:
        pass


@bot.event
async def on_message(msg):
    try:
        if USER_IDS[msg.author._user.id] == 'ben':
            await msg.reply('suck a dick')
            return
    except Exception:
        pass

    await bot.process_commands(msg)


@bot.command(name='addmovie', help='add a movie to the plex')
async def addmovie(ctx, *args):
    if ctx.message.channel.id != PLEX_CHANNEL_ID:
        return

    if not args:
        await reply(ctx, 'usage: !addmovie KEYWORDS...')
        return

    logger.info(f'got !addmovie command from user {ctx.message.author.name}: {ctx.message.content}')

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

        if not radarr.add_movie(movie, ctx.message.author._user.id):
            await reply(resp, f'{movie} is already on the plex (idiot)')
            continue

        logger.info(f'{ctx.message.author.name} has added the movie {movie.full_title} to the plex')

        send_push(
            f'{ctx.message.author.name} has added the movie {movie.full_title}')

        await reply(resp, f'added movie {movie} to the plex')


@bot.command(name='delmovie', help='delete a movie from the plex')
async def delmovie(ctx, *args):
    if ctx.message.channel.id != PLEX_CHANNEL_ID:
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

        send_push(f'{ctx.message.author.name} has deleted the movie {movie.full_title}')

        await reply(resp, f'deleted movie {movie} from the plex')


@commands.cooldown(1, 10)  # one time every 10 seconds
@bot.command(name='downloads', help='see the status of movie downloads')
async def downloads(ctx):
    if ctx.message.channel.id != PLEX_CHANNEL_ID:
        return

    # TODO: add sabnzbd

    c = TransmissionClient(host='localhost', port=9091,
                           username='transmission', password='password')

    logger.debug('connected to transmission rpc')

    torrents = c.get_torrents()

    if not torrents:
        await reply(ctx, 'there are no pending downloads')
        return

    name_pattern = re.compile(r'(?P<title>(?:\w+\.)+)(?P<year>[12]\d\d\d)[^p]')

    msg = []

    for torrent in sorted(torrents, key=lambda t: t.progress, reverse=True):
        if torrent.status == 'downloading':
            downloaded = torrent.size_when_done - torrent.left_until_done

            if torrent.left_until_done == 0:
                continue

            name = torrent.name

            match = name_pattern.search(name)

            if match:
                name = ' '.join(match.group('title').split('.')).strip()
                name += f' ({match.group("year")})'

            movie_msg = (
                f'{name}: {torrent.progress:.1f}% done '
                f'({downloaded / 1024**3:.2f}/{torrent.size_when_done / 1024**3:.2f} GB)\n'
                f'remaining availability: {torrent.desired_available/torrent.left_until_done*100:.1f}%, '
                f'eta: {torrent.format_eta()}\n')

            msg.append(movie_msg)

    await reply(ctx, '\n'.join(msg), title='download progress')


@commands.cooldown(1, 60)
@bot.command(name='searchmissing', help='search for missing movies that have been added')
async def searchmissing(ctx):
    if ctx.message.channel.id != PLEX_CHANNEL_ID:
        return

    if 'plex-admin' not in [role.name for role in ctx.message.author.roles]:
        await reply(ctx, f'user {ctx.message.author.name} does not have permission to use this command', error=True)
        return

    # TODO: get status? maybe progress bar?

    radarr.search_missing()

    await reply(ctx, 'searching for missing movies...')


@commands.cooldown(1, 60, commands.BucketType.user)
@bot.command(name='quota', help='see your used space on the plex')
async def quota(ctx):
    if ctx.message.channel.id != PLEX_CHANNEL_ID:
        return

    used = radarr.get_quota_amount(ctx.message.author._user.id) / 1024**3

    maximum = 0

    try:
        maximum = QUOTAS[ctx.message.author._user.id]
    except Exception:
        pass

    pct = used / maximum * 100 if maximum != 0 else 100

    msg = f'you have added {used:.2f}/{maximum:.2f} GB ({pct:.1f}%) of useless crap to the plex'

    await reply(ctx, msg)


@commands.cooldown(1, 60)
@bot.command(name='quotas', help="see everyone's used space on the plex")
async def quotas(ctx):
    if ctx.message.channel.id != PLEX_CHANNEL_ID:
        return

    msg = []

    for key, total in QUOTAS.items():
        used = radarr.get_quota_amount(key) / 1024**3
        total = QUOTAS[key]

        pct = used / total * 100 if total != 0 else 100

        msg.append(f'{USER_IDS[key]}: {used:.2f}/{total:.2f} GB ({pct:.1f}%)')

    await reply(ctx, '\n'.join(sorted(msg)), title='quotas of users who have bought space')


if __name__ == '__main__':
    bot.run(DISCORD_TOKEN)
