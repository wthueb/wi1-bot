import argparse
from time import sleep

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.webhook.config import config


def rescan_radarr() -> None:
    radarr = Radarr.from_config(config.radarr)

    all_movies = radarr.get_movies()
    all_movies.sort(key=lambda m: m["title"])

    for movie in all_movies:
        print(f"Rescanning {movie['title']}...")
        radarr.refresh_movie(movie["id"])
        sleep(3)


def rescan_sonarr() -> None:
    sonarr = Sonarr.from_config(config.sonarr)

    all_series = sonarr.get_series()
    all_series.sort(key=lambda s: s["title"])

    for series in all_series:
        print(f"Rescanning {series['title']}...")
        sonarr.rescan_series(series["id"])
        sleep(5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rescan all movies/shows")

    parser.add_argument("service", nargs="?", choices=["radarr", "sonarr"], help="radarr or sonarr")

    args = parser.parse_args()

    if args.service == "radarr":
        rescan_radarr()
    elif args.service == "sonarr":
        rescan_sonarr()
    else:
        rescan_radarr()
        rescan_sonarr()


if __name__ == "__main__":
    main()
