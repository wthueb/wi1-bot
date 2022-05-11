import argparse

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("nickname")
    parser.add_argument("discord_id")

    args = parser.parse_args()

    radarr = Radarr(config["radarr"]["url"], config["radarr"]["api_key"])
    sonarr = Sonarr(config["sonarr"]["url"], config["sonarr"]["api_key"])

    radarr._radarr.create_tag(f"{args.nickname}: {args.discord_id}")
    sonarr._sonarr.create_tag(f"{args.nickname}: {args.discord_id}")


if __name__ == "__main__":
    main()
