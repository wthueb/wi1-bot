import argparse

import transcoder


parser = argparse.ArgumentParser(description='add item to transcode queue')

parser.add_argument('path', help='file path to transcode')

args = parser.parse_args()

quality = transcoder.TranscodeQuality(2_000_000, 'aac', 2)

item = transcoder.TranscodeItem(args.path, quality, None)

transcoder.transcode_queue.put(item)
