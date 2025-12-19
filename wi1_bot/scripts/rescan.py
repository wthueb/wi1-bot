import argparse
from time import sleep
from typing import cast

from wi1_bot.arr.radarr import Radarr
from wi1_bot.arr.sonarr import Sonarr
from wi1_bot.config import config


def rescan_radarr() -> None:
    radarr = Radarr(str(config.radarr.url), config.radarr.api_key)

    all_movies = radarr._radarr.get_movie()  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType, reportPrivateUsage]
    assert isinstance(all_movies, list)
    all_movies.sort(key=lambda m: cast(str, m["title"]))  # pyright: ignore[reportUnknownMemberType, reportUnknownLambdaType]

    for movie in all_movies:  # pyright: ignore[reportUnknownVariableType]
        assert isinstance(movie, dict)
        print(f"Rescanning {movie['title']}...")
        radarr.refresh_movie(movie["id"])  # pyright: ignore[reportUnknownArgumentType]
        sleep(3)


def rescan_sonarr() -> None:
    sonarr = Sonarr(str(config.sonarr.url), config.sonarr.api_key)

    all_series = sonarr._sonarr.get_series()  # pyright: ignore[reportPrivateUsage]
    assert isinstance(all_series, list)
    all_series.sort(key=lambda s: cast(str, s["title"]))  # pyright: ignore[reportUnknownMemberType, reportUnknownLambdaType]

    for series in all_series:  # pyright: ignore[reportUnknownVariableType]
        assert isinstance(series, dict)
        print(f"Rescanning {series['title']}...")
        sonarr.rescan_series(series["id"])  # pyright: ignore[reportUnknownArgumentType]
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
