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
    instance_name: str = Field(
        min_length=1, description="Instance name, must match Settings->General->Instance Name"
    )

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


class Quota(BaseModel):
    amount: float = Field(gt=0, description="Quota amount in GB")
    with_: list[int] = Field(
        default_factory=list,
        alias="with",
        description="Additional Discord user IDs that count toward this quota",
    )


class DiscordConfig(BaseModel):
    bot_token: str = Field(min_length=1, description="Discord bot token")
    channel_id: int = Field(gt=0, description="Discord channel ID for bot")
    admin_id: int = Field(gt=0, description="Discord admin user ID")
    bot_presence: str | None = Field(None, description="Bot presence/status text")
    quotas: dict[int, Quota] = Field(
        default_factory=dict, description="User quotas in GB by user ID"
    )

    @field_validator("quotas", mode="before")
    @classmethod
    def normalize_quotas(
        cls, v: dict[int, float | dict[str, object]] | None
    ) -> dict[int, dict[str, object]]:
        if v is None:
            return {}
        # backwards compatible: a bare number is shorthand for {"amount": number}
        return {
            user_id: {"amount": quota} if isinstance(quota, (int, float)) else quota
            for user_id, quota in v.items()
        }

    @field_validator("quotas", mode="after")
    @classmethod
    def validate_quota_membership(cls, v: dict[int, Quota]) -> dict[int, Quota]:
        # a Discord ID may belong to at most one quota group (as owner or member)
        owner_of: dict[int, int] = {}
        for owner_id, quota in v.items():
            for user_id in (owner_id, *quota.with_):
                if user_id in owner_of:
                    raise ValueError(
                        f"Discord ID {user_id} is assigned to more than one quota"
                        f" (groups {owner_of[user_id]} and {owner_id})"
                    )
                owner_of[user_id] = owner_id
        return v


class TranscodingProfile(BaseModel):
    video_params: str | None = Field(None, description="FFmpeg video parameters")
    audio_params: str | None = Field(None, description="FFmpeg audio parameters")
    languages: str | None = Field(None, description="Comma-separated ISO 639-2 language codes")
    keep_original_language: bool = Field(
        True,
        description="Keep a title's original-language tracks even if not in languages",
    )


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
    radarr4k: ArrConfig | None = None
    sonarr: ArrConfig
    sonarr4k: ArrConfig | None = None
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
