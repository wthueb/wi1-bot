from pathlib import Path

from wi1_bot.transcoder.config import RemotePathMapping
from wi1_bot.transcoder.paths import replace_remote_paths


class TestReplaceRemotePaths:
    def test_no_mappings(self) -> None:
        path = Path("/movies/The Matrix (1999)/movie.mkv")
        assert replace_remote_paths(path, []) == path

    def test_single_mapping_match(self) -> None:
        path = Path("/mnt/remote/movies/The Matrix (1999)/movie.mkv")
        mappings = [RemotePathMapping(remote=Path("/mnt/remote"), local=Path("/local"))]

        assert replace_remote_paths(path, mappings) == Path(
            "/local/movies/The Matrix (1999)/movie.mkv"
        )

    def test_single_mapping_no_match(self) -> None:
        path = Path("/movies/The Matrix (1999)/movie.mkv")
        mappings = [RemotePathMapping(remote=Path("/mnt/remote"), local=Path("/local"))]

        assert replace_remote_paths(path, mappings) == path

    def test_multiple_mappings_most_specific(self) -> None:
        path = Path("/mnt/remote/movies/action/The Matrix (1999)/movie.mkv")
        mappings = [
            RemotePathMapping(remote=Path("/mnt/remote"), local=Path("/local1")),
            RemotePathMapping(remote=Path("/mnt/remote/movies"), local=Path("/local2")),
            RemotePathMapping(remote=Path("/mnt/remote/movies/action"), local=Path("/local3")),
        ]

        assert replace_remote_paths(path, mappings) == Path("/local3/The Matrix (1999)/movie.mkv")

    def test_multiple_mappings_partial_match(self) -> None:
        path = Path("/mnt/remote/movies/The Matrix (1999)/movie.mkv")
        mappings = [
            RemotePathMapping(remote=Path("/mnt/remote/tv"), local=Path("/local1")),
            RemotePathMapping(remote=Path("/mnt/remote/movies"), local=Path("/local2")),
        ]

        assert replace_remote_paths(path, mappings) == Path("/local2/The Matrix (1999)/movie.mkv")
