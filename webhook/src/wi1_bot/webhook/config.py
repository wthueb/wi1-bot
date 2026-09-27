import re
from typing import Literal, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from wi1_bot.arr import ArrConfig
from wi1_bot.common import PushoverConfig
from wi1_bot.common.config import BaseServiceConfig


class GeneralConfig(BaseModel):
    log_format: Literal["logfmt", "json"] = Field(
        default="logfmt", description="Log output format: logfmt or json"
    )


class QueueCleanupConfig(BaseModel):
    enabled: bool = Field(
        default=False,
        description="Whether to remove completed custom-format downgrade downloads",
    )
    poll_interval: float = Field(
        default=60,
        gt=0,
        description="Seconds between Arr download queue cleanup scans",
    )


class IMDbPopularListConfig(BaseModel):
    include_languages: list[str] = Field(default_factory=list)
    exclude_languages: list[str] = Field(default_factory=list)

    @field_validator("include_languages", "exclude_languages")
    @classmethod
    def normalize_languages(cls, languages: list[str]) -> list[str]:
        normalized = [language.strip().lower() for language in languages]
        if any(re.fullmatch(r"[a-z]{2}", language) is None for language in normalized):
            raise ValueError("languages must be two-letter codes")
        return list(dict.fromkeys(normalized))

    @model_validator(mode="after")
    def reject_overlapping_languages(self) -> Self:
        if set(self.include_languages) & set(self.exclude_languages):
            raise ValueError("include_languages and exclude_languages must not overlap")
        return self


class WebhookConfig(BaseModel):
    port: int = Field(default=9000, gt=0, description="Port for the webhook/job API")
    heartbeat: float = Field(
        default=120,
        gt=0,
        description=(
            "Seconds between lease heartbeats a worker sends while transcoding"
            " (sent to the worker when it claims a job)"
        ),
    )
    missed_heartbeats: int = Field(
        default=3,
        gt=0,
        description=(
            "How many heartbeats a claimed job may miss before another worker may"
            " reclaim it; the lease is heartbeat * (missed_heartbeats + 0.5) seconds"
        ),
    )
    queue_cleanup: QueueCleanupConfig = Field(default_factory=QueueCleanupConfig)
    imdb_popular_list: IMDbPopularListConfig = Field(default_factory=IMDbPopularListConfig)

    @property
    def lease_secs(self) -> float:
        # the extra half-interval keeps the lease alive while the last heartbeat is in
        # flight, so a job isn't reclaimed just because a heartbeat is mid-send
        return self.heartbeat * (self.missed_heartbeats + 0.5)


class Config(BaseServiceConfig):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    radarr: ArrConfig
    radarr4k: ArrConfig | None = None
    sonarr: ArrConfig
    sonarr4k: ArrConfig | None = None
    pushover: PushoverConfig | None = None
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)


config = Config()  # type: ignore[call-arg]
