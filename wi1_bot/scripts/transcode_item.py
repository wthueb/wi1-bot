import argparse

from wi1_bot.config import config
from wi1_bot.transcoder import queue


def main():
    parser = argparse.ArgumentParser(description="add item to transcode queue")

    parser.add_argument("path", help="file path to transcode")

    args = parser.parse_args()

    qp = config["transcoding"]["profiles"]["good"]

    queue.add(
        path=args.path,
        video_codec=qp["video_codec"],
        video_bitrate=qp["video_bitrate"],
        audio_codec=qp["audio_codec"],
        audio_channels=qp["audio_channels"],
        audio_bitrate=qp["audio_bitrate"],
    )

    print("place in queue:", queue.size)


if __name__ == "__main__":
    main()
