import logging
import logging.handlers
import multiprocessing
import os.path

from flask import Flask, request
import yaml

from radarr import Radarr
import push
import transcoder


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)

app = Flask(__name__)

logger = logging.getLogger('wi1-bot.arr_webhook')
logger.setLevel(logging.DEBUG)

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])


def on_grab(req: dict) -> None:
    push.send(
        req['release']['releaseTitle'],
        title=f"file grabbed ({req['downloadClient']})")


def on_download(req: dict) -> None:
    movie_folder = req['movie']['folderPath']
    basename = req['movieFile']['relativePath']

    push.send(basename, title='file downloaded')

    path = os.path.join(movie_folder, basename)

    movie_json = radarr._radarr.get_movie_by_movie_id(req['movie']['id'])

    quality_profile = radarr.get_quality_profile_name(movie_json['qualityProfileId'])

    if quality_profile not in config['transcoding']:
        return

    quality = transcoder.TranscodeQuality(
        video_bitrate=config['transcoding'][quality_profile]['video_bitrate'],
        audio_codec=config['transcoding'][quality_profile]['audio_codec'],
        audio_channels=config['transcoding'][quality_profile]['audio_channels'])

    transcode_item = transcoder.TranscodeItem(movie_json['id'], path, quality)

    transcoder.transcode_queue.put(transcode_item)


@app.route('/', methods=['POST'])
def index():
    if request.json is None or 'eventType' not in request.json:
        return '', 400

    logger.debug(f'got request: {request.json}')

    if request.json['eventType'] == 'Grab':
        on_grab(request.json)
    elif request.json['eventType'] == 'Download':
        on_download(request.json)

    return '', 200


def run(logging_queue: multiprocessing.Queue) -> None:
    queue_handler = logging.handlers.QueueHandler(logging_queue)

    logger.addHandler(queue_handler)

    transcoder.start()

    logger.debug('starting webhook listener')

    app.run(host='localhost', port=9000)


if __name__ == '__main__':
    app.run(host='localhost', port=9000)
