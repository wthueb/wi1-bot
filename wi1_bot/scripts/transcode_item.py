import argparse
from typing import Any, Mapping

from wi1_bot.config import config
from wi1_bot.transcoder import queue


def main() -> None:
    parser = argparse.ArgumentParser(description="add item to transcode queue")

    parser.add_argument("path", help="file path to transcode")

    args = parser.parse_args()

    if "transcoding" not in config:
        raise ValueError("transcoding not configured")

    qp = config["transcoding"]["profiles"]["good"]

    def get_key(d: Mapping[str, Any], k: str) -> Any | None:
        try:
            return d[k]
        except KeyError:
            return None

    queue.add(
        path=args.path,
        copy_all_streams=get_key(qp, "copy_all_streams"),
        video_codec=get_key(qp, "video_codec"),
        video_bitrate=get_key(qp, "video_bitrate"),
        audio_codec=get_key(qp, "audio_codec"),
        audio_channels=get_key(qp, "audio_channels"),
        audio_bitrate=get_key(qp, "audio_bitrate"),
    )

    print("place in queue:", queue.size)


if __name__ == "__main__":
    main()
