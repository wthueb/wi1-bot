import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

import yaml

from radarr import Radarr
from sonarr import Sonarr


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)


parser = argparse.ArgumentParser()

parser.add_argument('nickname')
parser.add_argument('discord_id')

args = parser.parse_args()

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])
sonarr = Sonarr(config['sonarr']['url'], config['sonarr']['api_key'])

radarr._radarr.create_tag(f'{args.nickname}: {args.discord_id}')
sonarr._sonarr.create_tag(f'{args.nickname}: {args.discord_id}')
