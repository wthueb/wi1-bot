#!/usr/bin/env bash

# take first 5 seconds
# black out video stream 0 (keep other video streams)
# mute audio stream 0 (remove other audio streams)
# keep subtitles
# remove metadata and chapters
ffmpeg -t 5 -i $1 \
    -filter_complex "[0:v:0]drawbox=color=black:t=fill[v0]" \
    -af "volume=0" \
    -map "[v0]" -map 0:a:0 -map 0:s:0? -map 0:s:1? -map 0:v:1? \
    -c:v copy -c:v:0 libx264 -c:a eac3 -c:s copy \
    -map_metadata -1 -map_chapters -1 $2
