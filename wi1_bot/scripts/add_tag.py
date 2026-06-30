import argparse

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("nickname")
    parser.add_argument("discord_id")

    args = parser.parse_args()

    radarr = Radarr.from_config(config.radarr)
    sonarr = Sonarr.from_config(config.sonarr)

    radarr.create_tag(f"{args.nickname}: {args.discord_id}")
    sonarr.create_tag(f"{args.nickname}: {args.discord_id}")


if __name__ == "__main__":
    main()
