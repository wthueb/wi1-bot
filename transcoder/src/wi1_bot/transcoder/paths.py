import logging
from pathlib import Path

from wi1_bot.transcoder.config import RemotePathMapping

logger = logging.getLogger(__name__)


def replace_remote_paths(path: Path, mappings: list[RemotePathMapping]) -> Path:
    """Translate an Arr-native path into this worker's local filesystem path.

    Picks the most specific matching mapping (longest remote prefix). Returns the
    path unchanged when no mapping applies.
    """
    if not mappings:
        return path

    most_specific: RemotePathMapping | None = None

    for mapping in mappings:
        if path.is_relative_to(mapping.remote):
            mapping_len = len(mapping.remote.parts)
            most_specific_len = len(most_specific.remote.parts) if most_specific is not None else 0

            if mapping_len > most_specific_len:
                most_specific = mapping

    if most_specific is not None:
        remote_path = path
        path = most_specific.local / path.relative_to(most_specific.remote)

        logger.debug(f"replaced remote path mapping: {remote_path} -> {path}")

    return path
