import os

from flask import Flask, request

import push


app = Flask(__name__)


def on_grab(req: dict) -> None:
    push.send(
        req['release']['releaseTitle'],
        title=f'file grabbed ({req["downloadClient"]})')


def on_download(req: dict) -> None:
    push.send(req['movieFile']['sceneName'], title='file downloaded')

    movie_folder = req['movie']['folderPath']

    path = os.path.join(movie_folder, req['movieFile']['relativePath'])

    # TODO: transcode (using ffmpeg-python?)


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
