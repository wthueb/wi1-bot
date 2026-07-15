import os
from pathlib import Path
from typing import override

from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)


class PushoverConfig(BaseModel):
    user_key: str = Field(min_length=1, description="Pushover user key")
    api_key: str = Field(min_length=1, description="Pushover application API key")
    devices: str = Field(min_length=1, description="Comma-separated device names")


def resolve_config_path() -> str:
    """Locate a service's YAML config file.

    Priority (high to low): ``WB_CONFIG_PATH`` env var,
    ``$HOME/.config/wi1-bot/config.yaml``, ``$XDG_CONFIG_HOME/wi1-bot/config.yaml``,
    then ``./config.yaml``.
    """
    config_path = os.getenv("WB_CONFIG_PATH")

    if config_path is None:
        if home := os.getenv("HOME"):
            path = Path(home) / ".config" / "wi1-bot" / "config.yaml"
            if path.is_file():
                config_path = str(path.resolve())

        if xdg_config_home := os.getenv("XDG_CONFIG_HOME"):
            path = Path(xdg_config_home) / "wi1-bot" / "config.yaml"
            if path.is_file():
                config_path = str(path.resolve())

        if Path("config.yaml").is_file():
            config_path = "config.yaml"

    if config_path is None:
        raise FileNotFoundError(
            "could not find $WB_CONFIG_PATH, ./config.yaml,"
            " $XDG_CONFIG_HOME/wi1-bot/config.yaml or $HOME/.config/wi1-bot/config.yaml"
        )

    return config_path


class BaseServiceConfig(BaseSettings):
    """Base pydantic-settings config shared by every wi1-bot service.

    Loads from init args, ``WB_``-prefixed env vars (``__`` nesting), then the YAML
    file located by :func:`resolve_config_path`. Each service subclasses this and
    declares only the fields it needs.
    """

    model_config = SettingsConfigDict(
        env_prefix="WB_",
        env_nested_delimiter="__",
        case_sensitive=False,
        extra="ignore",
    )

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
            YamlConfigSettingsSource(settings_cls, resolve_config_path()),
        )
