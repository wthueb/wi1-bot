import pathlib
import shutil

import requests

from wi1_bot.config import config

path = pathlib.Path("./tests/files/jellyfish-10-mbps-hd-h264.mkv")

shutil.copy(f"{path}.bak", path)

header = {
    "X-Api-Key": config["radarr"]["api_key"],
}

data = {
    "eventType": "Download",
    "movie": {
        "id": 1,  # just to get quality profile
        "folderPath": "./tests/files",
    },
    "movieFile": {"relativePath": path.name},
}

requests.post("http://localhost:9000/", json=data)
