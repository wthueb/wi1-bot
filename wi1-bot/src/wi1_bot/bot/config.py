from typing import Literal

from pydantic import BaseModel, Field, field_validator

from wi1_bot.arr import ArrConfig
from wi1_bot.common import PushoverConfig
from wi1_bot.common.config import BaseServiceConfig


class GeneralConfig(BaseModel):
    log_format: Literal["logfmt", "json"] = Field(
        default="logfmt", description="Log output format: logfmt or json"
    )


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


class Config(BaseServiceConfig):
    general: GeneralConfig = Field(default_factory=GeneralConfig)
    radarr: ArrConfig
    sonarr: ArrConfig
    discord: DiscordConfig
    pushover: PushoverConfig | None = None


config = Config()  # type: ignore[call-arg]
