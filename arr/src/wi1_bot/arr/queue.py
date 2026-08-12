from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ArrQueueItemNotFound(Exception):
    """The queue item disappeared before an attempted cleanup completed."""


class ArrQueueStatusMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: str = ""
    messages: list[str] = Field(default_factory=list)


class ArrQueueItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    id: int = Field(gt=0)
    title: str
    protocol: Literal["torrent", "usenet"]
    status: str
    tracked_download_status: str | None = Field(default=None, alias="trackedDownloadStatus")
    tracked_download_state: str | None = Field(default=None, alias="trackedDownloadState")
    status_messages: list[ArrQueueStatusMessage] = Field(
        default_factory=list,
        alias="statusMessages",
    )

    @property
    def is_custom_format_downgrade(self) -> bool:
        if self.status.casefold() != "completed":
            return False
        if (self.tracked_download_status or "").casefold() != "warning":
            return False
        if (self.tracked_download_state or "").casefold() not in {
            "importblocked",
            "importpending",
        }:
            return False

        prefix = "Not a Custom Format upgrade for existing"
        return any(
            message.startswith(prefix)
            for status_message in self.status_messages
            for message in status_message.messages
        )


class ArrQueuePage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    records: list[ArrQueueItem] = Field(default_factory=list)
    total_records: int | None = Field(default=None, ge=0, alias="totalRecords")


__all__ = [
    "ArrQueueItem",
    "ArrQueueItemNotFound",
    "ArrQueuePage",
    "ArrQueueStatusMessage",
]
