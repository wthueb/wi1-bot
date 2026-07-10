import argparse
from pathlib import Path

from wi1_bot.config import config
from wi1_bot.db import init_db
from wi1_bot.transcoder import queue


def main() -> None:
    if config.transcoding is None:
        raise ValueError("transcoding not configured")

    default_profile = next(iter(config.transcoding.profiles))

    parser = argparse.ArgumentParser(description="add item to transcode queue")

    parser.add_argument("path", nargs="+", help="file path to transcode")
    parser.add_argument(
        "-p",
        "--profile",
        default=default_profile,
        help=f"quality profile to transcode with (default: {default_profile})",
    )

    args = parser.parse_args()

    if args.profile not in config.transcoding.profiles:
        raise ValueError(f"unknown quality profile: {args.profile}")

    init_db()

    for path in args.path:
        path = Path(path).resolve()

        queue.add(
            path=str(path),
            quality_profile=args.profile,
        )

    print("queue size:", queue.size)


if __name__ == "__main__":
    main()
