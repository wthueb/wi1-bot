import os
import sys

sys.path.insert(0, os.getcwd())

import transcoder

print(transcoder.transcode_queue.size)
