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
    lease_secs: int = Field(
        default=900,
        gt=0,
        description=(
            "Seconds a claimed transcode job's lease stays valid before another worker"
            " may reclaim it (workers heartbeat to keep it alive)"
        ),
    )


class Config(BaseServiceConfig):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    radarr: ArrConfig
    radarr4k: ArrConfig | None = None
    sonarr: ArrConfig
    sonarr4k: ArrConfig | None = None
    pushover: PushoverConfig | None = None
    webhook: WebhookConfig = Field(default_factory=WebhookConfig)


config = Config()  # type: ignore[call-arg]
