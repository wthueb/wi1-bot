import argparse

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.config import config


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("nickname")
    parser.add_argument("discord_id")

    args = parser.parse_args()

    radarr = Radarr(str(config.radarr.url), config.radarr.api_key)
    sonarr = Sonarr(str(config.sonarr.url), config.sonarr.api_key)

    radarr._radarr.create_tag(f"{args.nickname}: {args.discord_id}")  # pyright: ignore[reportUnknownMemberType, reportPrivateUsage]
    sonarr._sonarr.create_tag(f"{args.nickname}: {args.discord_id}")  # pyright: ignore[reportPrivateUsage]


if __name__ == "__main__":
    main()
