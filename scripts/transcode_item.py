import argparse
import os
import sys

sys.path.insert(0, os.getcwd())

import sys,os
sys.path.insert(0, os.getcwd())
from transcoder import queue


parser = argparse.ArgumentParser(description="add item to transcode queue")

parser.add_argument("path", help="file path to transcode")

args = parser.parse_args()

queue.add(
    path=args.path,
    video_codec="hevc_nvenc",
    video_bitrate=2_000_000,
    audio_codec="aac",
    audio_channels=2,
    audio_bitrate="128k",
)

print("place in queue:", queue.size)
