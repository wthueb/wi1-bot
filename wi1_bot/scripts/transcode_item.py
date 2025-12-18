import argparse
import pathlib

from wi1_bot.config import config
from wi1_bot.transcoder import queue


def main() -> None:
    parser = argparse.ArgumentParser(description="add item to transcode queue")

    parser.add_argument("path", help="file path to transcode")

    args = parser.parse_args()

    if config.transcoding is None:
        raise ValueError("transcoding not configured")

    path = pathlib.Path(args.path).resolve()

    qp = config.transcoding.profiles["good"]

    queue.add(
        path=str(path),
        languages=qp.languages,
        video_params=qp.video_params,
        audio_params=qp.audio_params,
    )

    print("place in queue:", queue.size)


if __name__ == "__main__":
    main()
