import socket
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from wi1_bot.common.config import BaseServiceConfig


class RemotePathMapping(BaseModel):
    remote: Path = Field(description="Remote (Arr-native) path to map from")
    local: Path = Field(description="Local path to map to")


class GeneralConfig(BaseModel):
    log_format: Literal["logfmt", "json"] = Field(
        default="logfmt", description="Log output format: logfmt or json"
    )
    remote_path_mappings: list[RemotePathMapping] = Field(default_factory=list)


class TranscodingFallback(BaseModel):
    video_params: str | None = Field(None, description="FFmpeg video parameters")
    audio_params: str | None = Field(None, description="FFmpeg audio parameters")
    hwaccel: str | None = Field(
        None,
        description=(
            "FFmpeg hardware acceleration for the fallback; omit for software"
            " decoding (e.g. to recover from a hardware-decoding failure)"
        ),
    )


class TranscodingProfile(BaseModel):
    video_params: str | None = Field(None, description="FFmpeg video parameters")
    audio_params: str | None = Field(None, description="FFmpeg audio parameters")
    languages: str | None = Field(None, description="Comma-separated ISO 639-2 language codes")
    keep_original_language: bool = Field(
        True,
        description="Keep a title's original-language tracks even if not in languages",
    )
    hwaccel: str | None = Field(
        None,
        description="FFmpeg hardware acceleration for this profile; omit for software decoding",
    )
    fallback: TranscodingFallback | None = Field(
        None, description="FFmpeg parameters to retry with once if a transcode fails"
    )


class TranscodingConfig(BaseModel):
    profiles: dict[str, TranscodingProfile] = Field(description="Transcoding profiles by name")

    @field_validator("profiles")
    @classmethod
    def validate_profiles(cls, v: dict[str, TranscodingProfile]) -> dict[str, TranscodingProfile]:
        if not v:
            raise ValueError("At least one transcoding profile must be defined")
        return v


class WorkerConfig(BaseModel):
    webhook_url: str = Field(description="Base URL of the wi1-bot-webhook job server")
    worker_name: str = Field(
        default_factory=socket.gethostname,
        description="Identifier reported when claiming jobs (defaults to the hostname)",
    )
    poll_interval: float = Field(
        default=3, gt=0, description="Seconds to wait between polling for jobs"
    )
    heartbeat_interval: float = Field(
        default=120, gt=0, description="Seconds between lease heartbeats while transcoding"
    )
    tmp_dir: Path | None = Field(
        default=None, description="Directory for in-progress transcodes (default: system temp)"
    )


class Config(BaseServiceConfig):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    transcoding: TranscodingConfig
    worker: WorkerConfig


config = Config()  # type: ignore[call-arg]
