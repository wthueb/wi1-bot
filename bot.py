import logging
from logging.handlers import RotatingFileHandler
import re

import discord
from discord.ext import commands
from transmission_rpc import Client as TransmissionClient
from pushover import Client as PushoverClient

from radarr import Radarr

from config import *


logger = logging.getLogger()

logger.setLevel(logging.INFO)

formatter = logging.Formatter('%(asctime)s:%(filename)s:%(levelname)s | %(message)s')

file_handler = RotatingFileHandler('logs/wi1-bot.log', maxBytes=1024*1024*10, backupCount=10)
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)

logger.addHandler(file_handler)
logger.addHandler(stream_handler)

radarr = Radarr(RADARR_URL, RADARR_API_KEY)

pushover = PushoverClient(PUSHOVER_USER_KEY, api_token=PUSHOVER_API_KEY)

bot = commands.Bot(intents=discord.Intents.all(), command_prefix='!')


def send_push(msg, priority=0):
    pushover.send_message(msg, priority=priority, device=PUSHOVER_DEVICES)


def movie_text(movie):
    return f'[{movie["title"]} ({movie["year"]})](https://www.themoviedb.org/movie/{movie["tmdbId"]})'


async def reply(ctx, message, title=None, error=False):
    embed = discord.Embed(title=title, description=message,
                          color=discord.Color.red() if error else discord.Color.blue())

    await ctx.reply(embed=embed)


@bot.event
async def on_ready():
    await bot.change_presence(activity=discord.Activity(
        type=discord.ActivityType.watching,
        name="david cronenberg's 1996 pièce de résistance, crash"))


@bot.command(name='addmovie', help='add a movie to the plex')
async def _addmovie(ctx, *args):
    if 'plex' not in [role.name for role in ctx.message.author.roles]:
        await reply(ctx, f'user {ctx.message.author.name} does not have permission to use this command', error=True)

        return

    if len(args) == 0:
        await reply(ctx, 'usage: !addmovie KEYWORDS...')

        return

    logger.info(f'got !addmovie command from user {ctx.message.author.name}: {ctx.message.content}')

    query = ' '.join(args)

    possible = radarr.lookup_movie(query)

    if len(possible) == 0:
        await reply(ctx, f'could not find the movie with the query: {query}', error=True)

        return

    movie_list = [f'{i+1}. {movie_text(movie)}' for i, movie in enumerate(possible)]

    await reply(ctx, '\n'.join(movie_list), title='type in the number of the movie to add, or type c to cancel')

    def check(resp):
        return (resp.author == ctx.message.author and resp.channel == ctx.message.channel and
                (resp.content.strip().isdigit() or resp.content.strip().lower() == 'c'))

    resp = None

    try:
        resp = await bot.wait_for('message', check=check, timeout=30)
    except Exception:
        await reply(ctx, 'timed out, add movie cancelled', error=True)

        return

    if resp.content.strip().lower() == 'c':
        await reply(resp, 'add movie cancelled')

        return

    idx = int(resp.content.strip()) - 1

    if idx < 0 or idx >= len(possible):
        await reply(resp, f'invalid index ({idx + 1}), add movie cancelled', error=True)

        return

    movie = possible[idx]

    if not radarr.add_movie(movie["tmdbId"]):
        await reply(resp, f'{movie_text(movie)} is already on the plex (idiot)')

        return

    # TODO: database

    logger.info(f'{ctx.message.author.name} has added the movie {movie_text(movie)} to the plex')

    send_push(f'{ctx.message.author.name} has added the movie {movie["title"]} ({movie["year"]})')

    await reply(resp, f'added movie {movie_text(movie)} to the plex')


@bot.command(name='delmovie', help='delete a movie from the plex')
async def _delmovie(ctx, *args):
    if 'plex-admin' not in [role.name for role in ctx.message.author.roles]:
        await reply(ctx, f'user {ctx.message.author.name} does not have permission to use this command', error=True)

        return

    if len(args) == 0:
        await reply(ctx, 'usage: !delmovie KEYWORDS...')

        return

    logger.info(f'got !delmovie command from user {ctx.message.author.name}: {ctx.message.content}')

    query = ' '.join(args)

    possible = radarr.lookup_library(query)

    if len(possible) == 0:
        await reply(ctx, f'could not find the movie with the query: {query}', error=True)

        return

    movie_list = [f'{i+1}. {movie_text(movie)}' for i, movie in enumerate(possible)]

    await reply(ctx, '\n'.join(movie_list), title='type in the number of the movie to delete, or type c to cancel')

    def check(resp):
        return (resp.author == ctx.message.author and resp.channel == ctx.message.channel and
                (resp.content.strip().isdigit() or resp.content.strip().lower() == 'c'))

    resp = None

    try:
        resp = await bot.wait_for('message', check=check, timeout=30)
    except Exception:
        await reply(ctx, 'timed out, del movie cancelled', error=True)

        return

    if resp.content.strip().lower() == 'c':
        await reply(resp, 'del movie cancelled')

        return

    idx = int(resp.content.strip()) - 1

    if idx < 0 or idx >= len(possible):
        await reply(resp, f'invalid index ({idx + 1}), del movie cancelled', error=True)

        return

    movie = possible[idx]

    radarr.del_movie(movie['tmdbId'])

    # TODO: database

    logger.info(f'{ctx.message.author.name} has deleted the movie {movie_text(movie)} from the plex')

    send_push(f'{ctx.message.author.name} has deleted the movie {movie["title"]} ({movie["year"]})')

    await reply(resp, f'deleted movie {movie_text(movie)} from the plex')


@commands.cooldown(1, 10)  # one time every 10 seconds
@bot.command(name='downloads', help='see the status of movie downloads')
async def _downloads(ctx, *args):
    c = TransmissionClient(host='localhost', port=9091,
                           username='transmission', password='password')

    logger.debug('connected to transmission rpc')

    torrents = c.get_torrents()

    if not torrents:
        await reply(ctx, 'there are no pending downloads')
        return

    name_pattern = re.compile(r'(?P<title>(?:\w+\.)+)(?P<year>[12]\d\d\d)[^p]')

    msg = []

    for torrent in torrents:
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
                f'({downloaded/1024/1024/1024:.2f}/{torrent.size_when_done/1024/1024/1024:.2f} GB)\n'
                f'remaining availability: {torrent.desired_available/torrent.left_until_done*100:.1f}%, '
                f'eta: {torrent.format_eta()}\n')

            msg.append(movie_msg)

    await reply(ctx, '\n'.join(msg), title='download progress')

if __name__ == '__main__':
    bot.run(DISCORD_TOKEN)
