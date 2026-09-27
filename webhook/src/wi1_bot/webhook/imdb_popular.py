import requests
import structlog
from flask import Blueprint, Response, jsonify
from pydantic import BaseModel, Field, TypeAdapter, field_validator

from wi1_bot.webhook.config import config

blueprint = Blueprint("imdb_popular", __name__, url_prefix="/lists/imdb")
logger = structlog.get_logger(__name__)
_UPSTREAM_URL = "https://api.radarr.video/v1/list/imdb/popular"


class PopularMovie(BaseModel):
    tmdb_id: int = Field(alias="TmdbId", strict=True, gt=0)
    original_language: str = Field(alias="OriginalLanguage", strict=True)

    @field_validator("original_language")
    @classmethod
    def validate_language(cls, value: str) -> str:
        language = value.strip().lower()
        if len(language) != 2 or not language.isascii() or not language.isalpha():
            raise ValueError("original language must be a two-letter code")
        return language


_movies_adapter = TypeAdapter(list[PopularMovie])


@blueprint.get("/popular")
def imdb_popular_list() -> Response | tuple[dict[str, str], int]:
    try:
        response = requests.get(_UPSTREAM_URL, timeout=10)
        response.raise_for_status()
        movies = _movies_adapter.validate_python(response.json())
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "IMDb popular list fetch failed", error_type=type(exc).__name__, exc_info=True
        )
        return {"error": "IMDb popular list unavailable"}, 502

    filters = config.webhook.imdb_popular_list
    included = set(filters.include_languages)
    excluded = set(filters.exclude_languages)
    seen: set[int] = set()
    filtered: list[dict[str, int]] = []
    for movie in movies:
        if movie.tmdb_id in seen:
            continue
        seen.add(movie.tmdb_id)
        if (included and movie.original_language not in included) or (
            movie.original_language in excluded
        ):
            continue
        filtered.append({"id": movie.tmdb_id})

    return jsonify(filtered)
