import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import init_db
from wi1_bot.webhook.transcode_queue import queue

TargetName = Literal["radarr", "radarr4k", "sonarr", "sonarr4k"]
TargetKind = Literal["radarr", "sonarr"]


@dataclass(frozen=True)
class MetadataTarget:
    name: TargetName
    kind: TargetKind
    client: Radarr | Sonarr


@dataclass(frozen=True)
class TranscodeMetadata:
    quality_profile: str
    original_language: str | None


def _targets_from_config() -> list[MetadataTarget]:
    targets = [
        MetadataTarget("radarr", "radarr", Radarr.from_config(config.radarr)),
        MetadataTarget("sonarr", "sonarr", Sonarr.from_config(config.sonarr)),
    ]
    if config.radarr4k is not None:
        targets.insert(
            1,
            MetadataTarget("radarr4k", "radarr", Radarr.from_config(config.radarr4k)),
        )
    if config.sonarr4k is not None:
        targets.append(MetadataTarget("sonarr4k", "sonarr", Sonarr.from_config(config.sonarr4k)))
    return targets


def _json_path(item: dict[str, Any], key: str) -> Path | None:
    value = item.get(key)
    if not isinstance(value, str) or not value:
        return None
    return Path(value).resolve()


def _is_below_arr_root(path: Path, client: Radarr | Sonarr) -> bool:
    return any(
        root_path is not None and path.is_relative_to(root_path)
        for root in client.get_root_folders()
        if (root_path := _json_path(root, "path")) is not None
    )


def _metadata_from_item(item: dict[str, Any], client: Radarr | Sonarr) -> TranscodeMetadata:
    profile_id = item.get("qualityProfileId")
    if not isinstance(profile_id, int):
        raise TypeError("Arr item qualityProfileId must be an integer")

    language = item.get("originalLanguage")
    original_language: str | None = None
    if isinstance(language, dict) and isinstance(language.get("name"), str):
        original_language = language["name"]

    return TranscodeMetadata(
        quality_profile=client.get_quality_profile_name(profile_id),
        original_language=original_language,
    )


def _resolve_radarr(path: Path, client: Radarr) -> TranscodeMetadata | None:
    if not _is_below_arr_root(path, client):
        return None

    for movie in client.get_movies():
        movie_path = _json_path(movie, "path")
        movie_id = movie.get("id")
        if movie_path is None or not isinstance(movie_id, int):
            continue
        if not path.is_relative_to(movie_path):
            continue

        for movie_file in client.get_movie_files(movie_id):
            if _json_path(movie_file, "path") == path:
                return _metadata_from_item(movie, client)

    return None


def _resolve_sonarr(path: Path, client: Sonarr) -> TranscodeMetadata | None:
    if not _is_below_arr_root(path, client):
        return None

    for series in client.get_series():
        series_path = _json_path(series, "path")
        series_id = series.get("id")
        if series_path is None or not isinstance(series_id, int):
            continue
        if not path.is_relative_to(series_path):
            continue

        for episode_file in client.get_episode_files(series_id):
            if _json_path(episode_file, "path") == path:
                return _metadata_from_item(series, client)

    return None


def resolve_metadata(path: Path, targets: list[MetadataTarget]) -> TranscodeMetadata | None:
    for target in targets:
        try:
            if target.kind == "radarr":
                assert isinstance(target.client, Radarr)
                metadata = _resolve_radarr(path, target.client)
            else:
                assert isinstance(target.client, Sonarr)
                metadata = _resolve_sonarr(path, target.client)
        except Exception:
            continue

        if metadata is not None:
            return metadata

    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="manually add an item to the transcode queue")

    parser.add_argument("path", nargs="+", help="file path to transcode (Arr-native path)")
    parser.add_argument(
        "-p",
        "--profile",
        required=True,
        help="fallback quality profile when the file cannot be resolved through Arr",
    )

    args = parser.parse_args()

    init_db()
    targets = _targets_from_config()

    for path in args.path:
        path = Path(path).resolve()
        metadata = resolve_metadata(path, targets)

        if metadata is None:
            metadata = TranscodeMetadata(
                quality_profile=args.profile,
                original_language=None,
            )
            print(
                f"warning: {path} not found; using fallback profile {args.profile!r} "
                "and no original language",
                file=sys.stderr,
            )

        queue.add(
            path=str(path),
            quality_profile=metadata.quality_profile,
            original_language=metadata.original_language,
        )

    print("queue size:", queue.size)


if __name__ == "__main__":
    main()
