import os
from typing import TypedDict

import yaml

_config_path: str | None = None

if os.path.isfile("config.yaml"):
    _config_path = "config.yaml"

if dir := os.getenv("XDG_CONFIG_HOME"):
    if os.path.isfile(os.path.join(dir, "wi1-bot", "config.yaml")):
        _config_path = os.path.join(dir, "wi1-bot", "config.yaml")

if home := os.getenv("HOME"):
    if os.path.isfile(os.path.join(home, ".config", "wi1-bot", "config.yaml")):
        _config_path = os.path.join(home, ".config", "wi1-bot", "config.yaml")

if _config_path is None:
    raise FileNotFoundError(
        "could not find ./config.yaml, $XDG_CONFIG_HOME/wi1-bot/config.yaml or"
        " $HOME/.config/wi1-bot/config.yaml"
    )


class ArrConfig(TypedDict):
    url: str
    api_key: str
    root_folder: str


class PushoverConfig(TypedDict):
    user_key: str
    api_key: str
    devices: str


# FIXME: python 3.11 supports typing.NotRequired (PEP 655)

# from typing import NotRequired

# class DiscordConfig(TypedDict):
#     bot_token: str
#     channel_id: int
#     admin_id: int
#     bot_presence: NotRequired[str]
#     quotas: NotRequired[dict[int, float]]


# class TranscodingProfile(TypedDict):
#     video_codec: NotRequired[str]
#     video_bitrate: NotRequired[int]
#     audio_codec: NotRequired[str]
#     audio_channels: NotRequired[int]
#     audio_bitrate: NotRequired[str]


# class TranscodingConfig(TypedDict):
#     profiles: dict[str, TranscodingProfile]
#     hwaccel: NotRequired[str]


# class Config(TypedDict):
#     radarr: ArrConfig
#     sonarr: ArrConfig
#     discord: DiscordConfig
#     pushover: NotRequired[PushoverConfig]
#     transcoding: NotRequired[TranscodingConfig]


class DiscordConfigOptional(TypedDict, total=False):
    bot_presence: str
    quotas: dict[int, float]


class DiscordConfig(DiscordConfigOptional):
    bot_token: str
    channel_id: int
    admin_id: int


class TranscodingProfile(TypedDict, total=False):
    copy_all_streams: bool
    video_codec: str
    video_bitrate: int
    audio_codec: str
    audio_channels: int
    audio_bitrate: str


class TranscodingConfigOptional(TypedDict, total=False):
    hwaccel: str  # optional


class TranscodingConfig(TranscodingConfigOptional):
    profiles: dict[str, TranscodingProfile]


class ConfigOptional(TypedDict, total=False):
    pushover: PushoverConfig  # optional
    transcoding: TranscodingConfig  # optional


class Config(ConfigOptional):
    radarr: ArrConfig
    sonarr: ArrConfig
    discord: DiscordConfig


with open(_config_path, "r") as f:
    config: Config = yaml.load(f, Loader=yaml.SafeLoader)
