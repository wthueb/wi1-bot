from typing import Literal

from pydantic import BaseModel, Field

from wi1_bot.arr import ArrConfig
from wi1_bot.common import PushoverConfig
from wi1_bot.common.config import BaseServiceConfig


class GeneralConfig(BaseModel):
    log_format: Literal["logfmt", "json"] = Field(
        default="logfmt", description="Log output format: logfmt or json"
    )


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
