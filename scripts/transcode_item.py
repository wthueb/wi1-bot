import argparse

from transcoder import queue


parser = argparse.ArgumentParser(description="add item to transcode queue")

parser.add_argument("path", help="file path to transcode")

args = parser.parse_args()

queue.add(
    path=args.path,
    video_bitrate=2_000_000,
    audio_codec="aac",
    audio_channels=2,
    audio_bitrate="128k",
)

print("place in queue:", queue.size)
