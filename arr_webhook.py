import os

from flask import Flask, request
from pushover import Client as PushoverClient

from config import PUSHOVER_USER_KEY, PUSHOVER_API_KEY


app = Flask(__name__)

pushover = PushoverClient(PUSHOVER_USER_KEY, api_token=PUSHOVER_API_KEY)


#  {
#      "movie": {
#          "id": 1357,
#          "title": "Spooky Buddies",
#          "year": 2011,
#          "releaseDate": "2011-08-15",
#          "folderPath": "/media/plex/movies/Spooky Buddies (2011)",
#          "tmdbId": 70587,
#          "imdbId": "tt1792131",
#      },
#      "remoteMovie": {
#          "tmdbId": 70587,
#          "imdbId": "tt1792131",
#          "title": "Spooky Buddies",
#          "year": 2011,
#      },
#      "release": {
#          "quality": "WEBDL-1080p",
#          "qualityVersion": 1,
#          "releaseGroup": "monkee",
#          "releaseTitle": "Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee",
#          "indexer": "nzbhydra2",
#          "size": 5310433000,
#      },
#      "downloadClient": "SABnzbd",
#      "downloadId": "SABnzbd_nzo_ejo29mhp",
#      "eventType": "Grab",
#  }

#  {
#      "movie": {
#          "id": 1357,
#          "title": "Spooky Buddies",
#          "year": 2011,
#          "releaseDate": "2011-08-15",
#          "folderPath": "/media/plex/movies/Spooky Buddies (2011)",
#          "tmdbId": 70587,
#          "imdbId": "tt1792131",
#      },
#      "remoteMovie": {
#          "tmdbId": 70587,
#          "imdbId": "tt1792131",
#          "title": "Spooky Buddies",
#          "year": 2011,
#      },
#      "movieFile": {
#          "id": 2868,
#          "relativePath": "Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee.mkv",
#          "path": "/media/plex/downloads/completed/radarr/Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee/Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee.mkv",
#          "quality": "WEBDL-1080p",
#          "qualityVersion": 1,
#          "releaseGroup": "monkee",
#          "sceneName": "Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee",
#          "indexerFlags": "0",
#          "size": 4562386952,
#      },
#      "isUpgrade": True,
#      "downloadId": "SABnzbd_nzo_ejo29mhp",
#      "deletedFiles": [
#          {
#              "id": 2624,
#              "relativePath": "Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee.mkv",
#              "path": "/media/plex/movies/Spooky Buddies (2011)/Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee.mkv",
#              "quality": "WEBDL-1080p",
#              "qualityVersion": 1,
#              "releaseGroup": "monkee",
#              "sceneName": "Spooky.Buddies.2011.1080p.NF.WEB-DL.DD5.1.x264-monkee",
#              "indexerFlags": "0",
#              "size": 4562386952,
#          }
#      ],
#      "eventType": "Download",
#  }

def on_grab(req: dict) -> None:
    pushover.send_message(
        req['release']['releaseTitle'],
        title=f'file grabbed ({req["downloadClient"]})')


def on_download(req: dict) -> None:
    pushover.send_message(req['movieFile']['sceneName'], title='file downloaded')

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
