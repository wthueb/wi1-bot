import os
from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, field_validator
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)
from typing_extensions import override

_config_path = os.getenv("WB_CONFIG_PATH")

if _config_path is None:
    if home := os.getenv("HOME"):
        _path = Path(home) / ".config" / "wi1-bot" / "config.yaml"
        if _path.is_file():
            _config_path = str(_path.resolve())

    if xdg_config_home := os.getenv("XDG_CONFIG_HOME"):
        _path = Path(xdg_config_home) / "wi1-bot" / "config.yaml"
        if _path.is_file():
            _config_path = str(_path.resolve())

    if Path("config.yaml").is_file():
        _config_path = "config.yaml"

if _config_path is None:
    raise FileNotFoundError(
        "could not find ./config.yaml, $XDG_CONFIG_HOME/wi1-bot/config.yaml or"
        + " $HOME/.config/wi1-bot/config.yaml"
    )


class RemotePathMapping(BaseModel):
    remote: Path = Field(description="Remote path to map from")
    local: Path = Field(description="Local path to map to")


class GeneralConfig(BaseModel):
    remote_path_mappings: list[RemotePathMapping] = Field(default_factory=list)


class ArrConfig(BaseModel):
    url: HttpUrl = Field(description="URL to Radarr/Sonarr dashboard")
    api_key: str = Field(min_length=1, description="API key for authentication")
    root_folder: Path = Field(description="Absolute path to root folder (from Arr's perspective)")

    @field_validator("root_folder")
    @classmethod
    def validate_absolute_path(cls, v: Path) -> Path:
        if not v.is_absolute():
            raise ValueError("root_folder must be an absolute path")
        return v


class PushoverConfig(BaseModel):
    user_key: str = Field(min_length=1, description="Pushover user key")
    api_key: str = Field(min_length=1, description="Pushover application API key")
    devices: str = Field(min_length=1, description="Comma-separated device names")


class DiscordConfig(BaseModel):
    bot_token: str = Field(min_length=1, description="Discord bot token")
    channel_id: int = Field(gt=0, description="Discord channel ID for bot")
    admin_id: int = Field(gt=0, description="Discord admin user ID")
    bot_presence: str | None = Field(None, description="Bot presence/status text")
    quotas: dict[int, float] = Field(
        default_factory=dict, description="User quotas in GB (user_id: quota)"
    )

    @field_validator("quotas", mode="before")
    @classmethod
    def validate_quotas(cls, v: dict[int, float] | None) -> dict[int, float]:
        if v is None:
            return {}
        for user_id, quota in v.items():
            if quota <= 0:
                raise ValueError(f"Quota for user {user_id} must be positive")
        return v


class TranscodingProfile(BaseModel):
    video_params: str | None = Field(None, description="FFmpeg video parameters")
    audio_params: str | None = Field(None, description="FFmpeg audio parameters")
    languages: str | None = Field(None, description="Comma-separated ISO 639-2 language codes")


class TranscodingConfig(BaseModel):
    profiles: dict[str, TranscodingProfile] = Field(description="Transcoding profiles by name")
    hwaccel: str | None = Field(None, description="FFmpeg hardware acceleration type")

    @field_validator("profiles")
    @classmethod
    def validate_profiles(cls, v: dict[str, TranscodingProfile]) -> dict[str, TranscodingProfile]:
        if not v:
            raise ValueError("At least one transcoding profile must be defined")
        return v


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WB_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    radarr: ArrConfig
    sonarr: ArrConfig
    discord: DiscordConfig
    pushover: PushoverConfig | None = None
    transcoding: TranscodingConfig | None = None

    @classmethod
    @override
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls, _config_path),
        )


config = Config()  # type: ignore[call-arg]
