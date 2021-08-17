import argparse

import yaml

from radarr import Radarr


with open('config.yaml', 'rb') as f:
    config = yaml.load(f, Loader=yaml.SafeLoader)


parser = argparse.ArgumentParser()

parser.add_argument('nickname')
parser.add_argument('discord_id')

args = parser.parse_args()

radarr = Radarr(config['radarr']['url'], config['radarr']['api_key'])

radarr._radarr.create_tag(f'{args.nickname}: {args.discord_id}')
