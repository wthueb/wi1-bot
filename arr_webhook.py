from datetime import timedelta
import os
import re
import shutil
import subprocess

from flask import Flask, request
import yaml

from radarr import Radarr
import push


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

app = Flask(__name__)

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])


def on_grab(req: dict) -> None:
    push.send(
        req['release']['releaseTitle'],
        title=f"file grabbed ({req['downloadClient']})")


def on_download(req: dict) -> None:
    push.send(req['movieFile']['relativePath'], title='file downloaded')

    movie_folder = req['movie']['folderPath']

    path = os.path.join(movie_folder, req['movieFile']['relativePath'])
    tmp_path = '/tmp/' + path.split('/')[-1]

    probe_command = [
        '/usr/bin/ffprobe',
        '-hide_banner',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        path
    ]

    probe_result = subprocess.run(probe_command, capture_output=True)

    duration = timedelta(seconds=float(probe_result.stdout.decode('utf-8').strip()))

    movie_json = radarr._radarr.get_movie_by_movie_id(req['movie']['id'])

    quality_profile = radarr.get_quality_profile_name(movie_json['qualityProfileId'])

    if quality_profile == 'best':
        return

    bitrate = None
    audio_codec = None

    if quality_profile == 'good':
        bitrate = 2_000_000
        audio_codec = 'aac'

    if not bitrate or not audio_codec:
        push.send(f'unknown quality profile: {quality_profile}')
        return

    # TODO: calculate compression amount ((video bitrate + audio bitrate) * duration / current size)
    # if compression amount not > config value, don't transcode
    # if compression amount > 1, don't transcode

    command = [
        '/usr/bin/ffmpeg',
        '-hide_banner',
        '-y',
        '-hwaccel', 'nvdec',
        '-hwaccel_output_format', 'cuda',
        '-i', path,
        '-max_muxing_queue_size', '1024',
        '-c:v',  'hevc_nvenc',
        '-preset', 'fast',
        '-profile:v', 'main',
        '-b:v', str(bitrate),
        '-maxrate', str(bitrate*2),
        '-bufsize', str(bitrate*2),
        '-c:a', 'aac',
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

    new_path = f"{'.'.join(path.split('.')[:-1])}-TRANSCODED.{path.split('.')[-1]}"

    shutil.move(tmp_path, new_path)
    os.remove(path)

    radarr._radarr.post_command('RefreshMovie', movieIds=[movie_json['id']])

    push.send(req['movieFile']['relativePath'], title='file transcoded')


@app.route('/', methods=['POST'])
def index():
    if request.json is None or 'eventType' not in request.json:
        return '', 400

    if request.json['eventType'] == 'Grab':
        on_grab(request.json)
    elif request.json['eventType'] == 'Download':
        on_download(request.json)

    return '', 200


def run() -> None:
    app.run(host='localhost', port=9000)


if __name__ == '__main__':
    run()
