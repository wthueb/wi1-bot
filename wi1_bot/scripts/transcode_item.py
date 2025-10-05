import argparse
import pathlib
from typing import Any, Mapping

from wi1_bot.config import config
from wi1_bot.transcoder import queue


def main() -> None:
    parser = argparse.ArgumentParser(description="add item to transcode queue")

    parser.add_argument("path", help="file path to transcode")

    args = parser.parse_args()

    if "transcoding" not in config:
        raise ValueError("transcoding not configured")

    path = pathlib.Path(args.path).resolve()

    qp = config["transcoding"]["profiles"]["good"]

    def get_key(d: Mapping[str, Any], k: str) -> Any | None:
        try:
            return d[k]
        except KeyError:
            return None

    queue.add(
        path=str(path),
        languages=get_key(qp, "languages"),
        video_params=get_key(qp, "video_params"),
        audio_params=get_key(qp, "audio_params"),
    )

    print("place in queue:", queue.size)


if __name__ == "__main__":
    main()
