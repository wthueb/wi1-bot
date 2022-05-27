import os
from typing import TypedDict

import yaml

_config_path: str | None = None

if os.path.isfile("config.yaml"):
    _config_path = "config.yaml"

if dir := os.getenv("XDG_CONFIG_HOME"):
    if os.path.isfile(os.path.join(dir, "wi1_bot", "config.yaml")):
        _config_path = os.path.join(dir, "wi1_bot", "config.yaml")

if home := os.getenv("HOME"):
    if os.path.isfile(os.path.join(home, ".config", "wi1_bot", "config.yaml")):
        _config_path = os.path.join(home, ".config", "wi1_bot", "config.yaml")

if _config_path is None:
    raise FileNotFoundError(
        "could not find ./config.yaml, $XDG_CONFIG_HOME/wi1_bot/config.yaml or"
        " $HOME/.config/wi1_bot/config.yaml"
    )


class ArrConfig(TypedDict):
    url: str
    api_key: str


class PushoverConfig(TypedDict):
    user_key: str
    api_key: str
    devices: str


# FIXME: python 3.11 supports typing.NotRequired (PEP 655), so we
# won't have to deal with this horrid mess of
# ___ConfigRequired followed by ___Config(___ConfigRequired, total=False)
class DiscordConfigRequired(TypedDict):
    bot_token: str
    channel_id: int
    admin_id: int


class DiscordConfig(DiscordConfigRequired, total=False):
    bot_presence: str  # optional
    quotas: dict[int, float]  # optional


class TranscodingProfile(TypedDict, total=False):
    video_codec: str  # optional
    video_bitrate: int  # optional
    audio_codec: str  # optional
    audio_channels: int  # optional
    audio_bitrate: str  # optional


class TranscodingConfigRequired(TypedDict):
    profiles: dict[str, TranscodingProfile]


class TranscodingConfig(TranscodingConfigRequired, total=False):
    hwaccel: str  # optional


class ConfigRequired(TypedDict):
    radarr: ArrConfig
    sonarr: ArrConfig
    discord: DiscordConfig


class Config(ConfigRequired, total=False):
    pushover: PushoverConfig  # optional
    transcoding: TranscodingConfig  # optional


with open(_config_path, "r") as f:
    config: Config = yaml.load(f, Loader=yaml.SafeLoader)
