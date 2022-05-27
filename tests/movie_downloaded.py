import shutil

import requests

from wi1_bot.config import config

shutil.copy(
    "./tests/files/jellyfish-10-mbps-hd-h264.mkv.bak",
    "./tests/files/jellyfish-10-mbps-hd-h264.mkv",
)

header = {
    "X-Api-Key": config["radarr"]["api_key"],
}

data = {
    "eventType": "Download",
    "movie": {
        "id": 1,  # just to get quality profile
        "folderPath": "./tests/files",
    },
    "movieFile": {"relativePath": "jellyfish-10-mbps-hd-h264.mkv"},
}

requests.post("http://localhost:9000/", json=data)
