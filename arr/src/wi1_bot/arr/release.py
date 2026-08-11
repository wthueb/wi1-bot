import json
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter, model_validator

ReleaseProtocol = Literal["torrent", "usenet"]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReleasePushConfigurationError(Exception):
    pass


class ReleasePushRequest(BaseModel):
    """The Radarr/Sonarr release-push fields sent by autobrr.

    Unknown fields are retained so additive autobrr API changes can pass through to
    downstream Arr instances without requiring an immediate wi1-bot release.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    title: NonEmptyText
    info_url: str | None = Field(default=None, alias="infoUrl")
    download_url: str | None = Field(default=None, alias="downloadUrl")
    magnet_url: str | None = Field(default=None, alias="magnetUrl")
    size: int = Field(default=0, ge=0)
    indexer: str = ""
    download_protocol: ReleaseProtocol = Field(alias="downloadProtocol")
    protocol: ReleaseProtocol
    publish_date: NonEmptyText = Field(alias="publishDate")
    download_client_id: int = Field(default=0, ge=0, alias="downloadClientId")
    download_client: str | None = Field(default=None, alias="downloadClient")
    indexer_flags: int = Field(default=0, ge=0, alias="indexerFlags")

    @model_validator(mode="after")
    def require_download_location(self) -> Self:
        if not self.download_url and not self.magnet_url:
            raise ValueError("downloadUrl or magnetUrl is required")
        return self

    def as_arr_payload(self) -> dict[str, object]:
        exclude = {"download_client_id"} if self.download_client_id == 0 else None
        return self.model_dump(mode="json", by_alias=True, exclude_none=True, exclude=exclude)

    @property
    def sensitive_urls(self) -> tuple[str, ...]:
        return tuple(url for url in (self.download_url, self.magnet_url) if url)


class ReleasePushResult(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    approved: bool
    rejected: bool
    temporarily_rejected: bool = Field(
        validation_alias="temporarilyRejected",
        serialization_alias="temporarilyRejected",
    )
    rejections: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.approved == self.rejected:
            raise ValueError("release push result must be either approved or rejected")
        if self.temporarily_rejected and not self.rejected:
            raise ValueError("only rejected releases can be temporarily rejected")
        return self

    def as_api_dict(self) -> dict[str, bool | list[str]]:
        return {
            "approved": self.approved,
            "rejected": self.rejected,
            "temporarilyRejected": self.temporarily_rejected,
            "rejections": self.rejections,
        }


class ReleasePushBadRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    severity: str = ""
    error_code: str = Field(default="", alias="errorCode")
    error_message: str = Field(default="", alias="errorMessage")
    property_name: str = Field(default="", alias="propertyName")
    attempted_value: object = Field(default="", alias="attemptedValue")

    def as_rejection(self) -> str:
        return (
            f"[{self.severity}: {self.error_code}] {self.property_name}: "
            f"{self.error_message} - got value: {self.attempted_value}"
        )


_RESULTS_ADAPTER = TypeAdapter(list[ReleasePushResult])
_BAD_REQUEST_ADAPTER = TypeAdapter(list[ReleasePushBadRequest])


def validate_release_push_results(value: object) -> list[ReleasePushResult]:
    results = _RESULTS_ADAPTER.validate_python(value)
    if not results:
        raise ValueError("release push returned no results")
    return results


def parse_release_push_bad_request(message: str) -> tuple[list[str], bool]:
    """Return formatted Arr validation reasons and whether client config is invalid."""

    responses = _BAD_REQUEST_ADAPTER.validate_python(json.loads(message))
    if not responses:
        raise ValueError("release push bad request returned no validation errors")

    invalid_download_client = any(
        response.property_name.casefold() in {"downloadclient", "downloadclientid"}
        for response in responses
    )
    return [response.as_rejection() for response in responses], invalid_download_client
