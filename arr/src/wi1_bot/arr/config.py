from pathlib import Path

from pydantic import BaseModel, Field, HttpUrl, field_validator


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
