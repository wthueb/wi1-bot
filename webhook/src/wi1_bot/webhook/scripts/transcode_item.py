import argparse
from pathlib import Path

from wi1_bot.webhook.db import init_db
from wi1_bot.webhook.transcode_queue import queue


def main() -> None:
    parser = argparse.ArgumentParser(description="manually add an item to the transcode queue")

    parser.add_argument("path", nargs="+", help="file path to transcode (Arr-native path)")
    parser.add_argument(
        "-p",
        "--profile",
        required=True,
        help="quality profile name to transcode with (resolved by the worker)",
    )

    args = parser.parse_args()

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
