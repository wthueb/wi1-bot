import os
import pathlib
from typing import NotRequired, TypedDict

import yaml

_config_path = os.getenv("WB_CONFIG_PATH")

if _config_path is None:
    if home := os.getenv("HOME"):
        _path = pathlib.Path(home) / ".config" / "wi1-bot" / "config.yaml"
        if _path.is_file():
            _config_path = str(_path.resolve())

    if xdg_config_home := os.getenv("XDG_CONFIG_HOME"):
        _path = pathlib.Path(xdg_config_home) / "wi1-bot" / "config.yaml"
        if _path.is_file():
            _config_path = str(_path.resolve())

    if pathlib.Path("config.yaml").is_file():
        _config_path = "config.yaml"

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


class DiscordConfig(TypedDict):
    bot_token: str
    channel_id: int
    admin_id: int
    bot_presence: NotRequired[str]
    quotas: NotRequired[dict[int, float]]


class TranscodingProfile(TypedDict):
    video_params: NotRequired[str]
    audio_params: NotRequired[str]
    languages: NotRequired[str]


class TranscodingConfig(TypedDict):
    profiles: dict[str, TranscodingProfile]
    hwaccel: NotRequired[str]


class RemotePathMapping(TypedDict):
    remote: str
    local: str


class GeneralConfig(TypedDict):
    remote_path_mappings: NotRequired[list[RemotePathMapping]]


class Config(TypedDict):
    general: NotRequired[GeneralConfig]  # optional
    radarr: ArrConfig
    sonarr: ArrConfig
    discord: DiscordConfig
    pushover: NotRequired[PushoverConfig]
    transcoding: NotRequired[TranscodingConfig]


with open(_config_path, "r") as f:
    config: Config = yaml.load(f, Loader=yaml.SafeLoader)
