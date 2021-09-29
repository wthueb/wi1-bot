from datetime import timedelta
import logging
import logging.handlers
import os
import re
import shutil
import subprocess

import persistqueue
import yaml

import push
from radarr import Radarr

with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

logger = logging.getLogger('wi1-bot.arr_webhook.transcoder')
logger.setLevel(logging.DEBUG)

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])

transcode_queue = persistqueue.Queue('transcode-queue')


class TranscodeQuality:
    def __init__(self, video_bitrate: int, audio_codec: str, audio_channels: int) -> None:
        self.video_bitrate = video_bitrate
        self.audio_codec = audio_codec
        self.audio_channels = audio_channels


class TranscodeItem:
    def __init__(self, movie_id: int, path: str, quality: TranscodeQuality) -> None:
        self.movie_id = movie_id
        self.path = path
        self.quality = quality


def do_transcode(item: TranscodeItem):
    filename = item.path.split('/')[-1]

    logger.info(f'starting transcode: {filename}')

    push.send(f'{filename}', title='starting transcode')

    probe_command = [
        '/usr/bin/ffprobe',
        '-hide_banner',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        item.path
    ]

    probe_result = subprocess.run(probe_command, capture_output=True)

    duration = timedelta(seconds=float(probe_result.stdout.decode('utf-8').strip()))

    # TODO: calculate compression amount ((video bitrate + audio bitrate) * duration / current size)
    # if compression amount not > config value, don't transcode
    # if compression amount > 1, don't transcode

    tmp_path = os.path.join('/tmp/', filename)

    command = [
        '/usr/bin/ffmpeg',
        '-hide_banner',
        '-y',
        '-hwaccel', 'nvdec',
        '-hwaccel_output_format', 'cuda',
        '-i', item.path,
        '-max_muxing_queue_size', '1024',
        '-c:v',  'hevc_nvenc',
        '-preset', 'fast',
        '-profile:v', 'main',
        '-b:v', str(item.quality.video_bitrate),
        '-maxrate', str(item.quality.video_bitrate*2),
        '-c:a', item.quality.audio_codec,
        '-ac', str(item.quality.audio_channels),
        '-c:s', 'copy',
        tmp_path
    ]

    proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, universal_newlines=True)

    pattern = re.compile(
        r'.*time=(?P<hours>\d+):(?P<minutes>\d+):(?P<seconds>\d+.?\d+)\s*bitrate.*speed=(?P<speed>(\d+)?(\.\d)?)x')

    for line in proc.stdout:  # type: ignore
        match = pattern.search(line)

        if not match:
            continue

        curtime = timedelta(
            hours=int(match.group('hours')),
            minutes=int(match.group('minutes')),
            seconds=float(match.group('seconds')))

        percent_done = curtime / duration

        speed = float(match.group('speed'))

        time_remaining = (duration - curtime) / speed

        # TODO

    folder = '/'.join(item.path.split('/')[:-1])

    new_filename = f"{'.'.join(filename.split('.')[:-1])}-TRANSCODED.{filename.split('.')[-1]}"

    new_path = os.path.join(folder, new_filename)

    shutil.move(tmp_path, new_path)
    os.remove(item.path)

    radarr.refresh_movie(item.movie_id)

    logger.info(f'finished transcode: {filename} -> {new_filename}')

    push.send(f'{filename} -> {new_filename}', title='file transcoded')


def run() -> None:
    logger.debug('starting transcoder')

    while True:
        logger.debug('waiting for queue item')

        item = transcode_queue.get()

        do_transcode(item)  # type: ignore

        transcode_queue.task_done()


if __name__ == '__main__':
    run()
