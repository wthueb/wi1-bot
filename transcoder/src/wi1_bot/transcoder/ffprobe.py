import json
import subprocess
from pathlib import Path
from typing import Literal, NotRequired, TypedDict, cast


class StreamTags(TypedDict):
    language: NotRequired[str]
    BPS: NotRequired[str]
    NUMBER_OF_FRAMES: NotRequired[str]
    NUMBER_OF_BYTES: NotRequired[str]
    _STATISTICS_WRITING_APP: NotRequired[str]
    _STATISTICS_WRITING_DATE_UTC: NotRequired[str]
    _STATISTICS_TAGS: NotRequired[str]
    DURATION: str
    title: NotRequired[str]
    ENCODER: NotRequired[str]
    FILENAME: NotRequired[str]
    MIMETYPE: NotRequired[str]


class Disposition(TypedDict):
    default: int
    dub: int
    original: int
    comment: int
    lyrics: int
    karaoke: int
    forced: int
    hearing_impaired: int
    visual_impaired: int
    clean_effects: int
    attached_pic: int
    timed_thumbnails: int
    non_diegetic: int
    captions: int
    descriptions: int
    metadata: int
    dependent: int
    still_image: int
    multilayer: int


class Stream(TypedDict):
    index: int
    codec_name: NotRequired[str]
    codec_long_name: str
    profile: NotRequired[str]
    codec_type: (
        Literal["video"]
        | Literal["audio"]
        | Literal["subtitle"]
        | Literal["data"]
        | Literal["attachment"]
        | Literal["nb"]
    )
    codec_tag_string: str
    codec_tag: str
    width: NotRequired[int]
    height: NotRequired[int]
    coded_width: NotRequired[int]
    coded_height: NotRequired[int]
    closed_captions: NotRequired[int]
    film_grain: NotRequired[int]
    has_b_frames: NotRequired[int]
    sample_aspect_ratio: NotRequired[str]
    display_aspect_ratio: NotRequired[str]
    pix_fmt: NotRequired[str]
    level: NotRequired[int]
    color_range: NotRequired[str]
    color_space: NotRequired[str]
    color_primaries: NotRequired[str]
    chroma_location: NotRequired[str]
    field_order: NotRequired[str]
    refs: NotRequired[int]
    is_avc: NotRequired[str]
    nal_length_size: NotRequired[str]
    r_frame_rate: str
    avg_frame_rate: str
    time_base: str
    start_pts: int
    start_time: str
    bits_per_raw_sample: NotRequired[str]
    extradata_size: NotRequired[int]
    disposition: Disposition
    tags: NotRequired[StreamTags]
    sample_fmt: NotRequired[str]
    sample_rate: NotRequired[str]
    channels: NotRequired[int]
    channel_layout: NotRequired[str]
    bits_per_sample: NotRequired[int]
    initial_padding: NotRequired[int]
    bit_rate: NotRequired[str]
    duration_ts: NotRequired[int]
    duration: NotRequired[str]


class FormatTags(TypedDict):
    title: str
    TMDB: str
    IMDB: str
    ENCODER: str


class Format(TypedDict):
    filename: str
    nb_streams: int
    nb_programs: int
    nb_stream_groups: int
    format_name: str
    format_long_name: str
    start_time: str
    duration: str
    size: str
    bit_rate: str
    probe_score: int
    tags: FormatTags


class FfprobeResult(TypedDict):
    streams: list[Stream]
    format: Format


class FfprobeException(Exception):
    pass


def ffprobe(path: Path | str) -> FfprobeResult:
    command = [
        "ffprobe",
        "-hide_banner",
        "-loglevel",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        str(path),
    ]

    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0:
        raise FfprobeException(f"ffprobe failed: {result.stderr.strip()}")

    result = json.loads(result.stdout)

    return cast(FfprobeResult, result)
