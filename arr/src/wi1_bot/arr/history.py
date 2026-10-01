from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DownloadOrigin = Literal["automatic", "manual", "unknown"]


class ArrGrabHistoryItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", hide_input_in_errors=True)

    download_id: str | None = Field(default=None, alias="downloadId")
    event_type: str | int = Field(alias="eventType")
    data: dict[str, str | None] = Field(default_factory=dict)

    def origin(self, download_id: str) -> DownloadOrigin:
        if self.download_id != download_id:
            return "unknown"
        if str(self.event_type).casefold() not in {"grabbed", "1"}:
            return "unknown"

        sources = [
            (value or "").strip().casefold()
            for key, value in self.data.items()
            if key.casefold() == "releasesource"
        ]
        if "interactivesearch" in sources:
            return "manual"
        if sources and all(
            source in {"rss", "search", "userinvokedsearch", "releasepush"} for source in sources
        ):
            return "automatic"
        return "unknown"


class ArrGrabHistoryPage(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore", hide_input_in_errors=True)

    records: list[ArrGrabHistoryItem]
    total_records: int | None = Field(default=None, ge=0, alias="totalRecords")


def read_download_origin(download_id: str, fetch_page: Callable[[int], object]) -> DownloadOrigin:
    if not download_id.strip():
        return "unknown"

    origins: set[DownloadOrigin] = set()
    record_count = 0
    page_number = 1
    while True:
        page = ArrGrabHistoryPage.model_validate(fetch_page(page_number))
        record_count += len(page.records)
        origins.update(item.origin(download_id) for item in page.records)
        if not page.records:
            if page.total_records is not None and record_count < page.total_records:
                return "unknown"
            break
        if page.total_records is not None:
            if record_count >= page.total_records:
                break
        elif len(page.records) < 100:
            break
        page_number += 1

    if "manual" in origins:
        return "manual"
    if origins == {"automatic"}:
        return "automatic"
    return "unknown"
