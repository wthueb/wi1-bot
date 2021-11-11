from datetime import timedelta
import logging
import logging.handlers
import os
import re
import shutil
import subprocess
import threading
from typing import Optional
from time import sleep

import persistqueue
import yaml

import push
from radarr import Radarr
from sonarr import Sonarr

with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

logger = logging.getLogger('wi1-bot.arr_webhook.transcoder')
logger.setLevel(logging.DEBUG)

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])
sonarr = Sonarr(config['sonarr']['url'], config['sonarr']['api_key'])

transcode_queue = persistqueue.SQLiteQueue('transcode-queue', multithreading=True)


class TranscodeQuality:
    def __init__(self, video_bitrate: int, audio_codec: str, audio_channels: int,
                 audio_bitrate: str) -> None:
        self.video_bitrate = video_bitrate
        self.audio_codec = audio_codec
        self.audio_channels = audio_channels
        self.audio_bitrate = audio_bitrate


class TranscodeItem:
    def __init__(self, path: str, quality: TranscodeQuality, update: Optional[tuple[str, int]] = None) -> None:
        self.path = path
        self.quality = quality
        self.update = update


def _do_transcode(item: TranscodeItem):
    basename = item.path.split('/')[-1]

    logger.info(f'starting transcode: {basename}')

    probe_command = [
        '/usr/bin/ffprobe',
        '-hide_banner',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        item.path
    ]

    probe_result = subprocess.run(probe_command, capture_output=True)

    try:
        duration = timedelta(seconds=float(probe_result.stdout.decode('utf-8').strip()))
    except ValueError:
        logger.warning(f'file does not exist: {item.path}, skipping transcoding')
        return

    push.send(f'{basename}', title='starting transcode')

    # TODO: calculate compression amount ((video bitrate + audio bitrate) * duration / current size)
    # if compression amount not > config value, don't transcode
    # if compression amount > 1, don't transcode

    tmp_path = os.path.join('/tmp/', basename)

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
        '-bufsize', str(item.quality.video_bitrate*2),
        '-c:a', item.quality.audio_codec,
        '-ac', str(item.quality.audio_channels),
        '-b:a', item.quality.audio_bitrate,
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

    ffmpeg_return = proc.wait()

    if ffmpeg_return != 0:
        raise Exception(f'ffmpeg exited with code {ffmpeg_return}')

    folder = '/'.join(item.path.split('/')[:-1])

    filename, extension = '.'.join(basename.split('.')[:-1]), basename.split('.')[-1]

    new_basename = f'{filename}-TRANSCODED.{extension}'

    new_path = os.path.join(folder, new_basename)

    if not os.path.exists(item.path):
        logger.info(f"file doesn't exist: {item.path}, deleting transcoded file")

        os.remove(tmp_path)

        return

    shutil.move(tmp_path, new_path)
    os.remove(item.path)

    if item.update:
        if item.update[0] == 'radarr':
            radarr.refresh_movie(item.update[1])
        elif item.update[0] == 'sonarr':
            sonarr.refresh_series(item.update[1])

    logger.info(f'finished transcode: {basename} -> {new_basename}')

    push.send(f'{basename} -> {new_basename}', title='file transcoded')


def _worker() -> None:
    logger.debug('starting transcoder')

    while True:
        logger.debug('waiting for queue item')

        item = transcode_queue.get()

        try:
            _do_transcode(item)  # type: ignore
        except Exception:
            logger.warning('got exception when trying to transcode', exc_info=True)
            sleep(3)
            continue

        transcode_queue.task_done()

        sleep(3)


def start() -> None:
    t = threading.Thread(target=_worker)
    t.daemon = True
    t.start()


if __name__ == '__main__':
    _worker()
