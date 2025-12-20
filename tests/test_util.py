from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from wi1_bot.arr.util import replace_remote_paths
from wi1_bot.config import GeneralConfig, RemotePathMapping


class TestReplaceRemotePaths:
    def test_no_mappings(self) -> None:
        path = Path("/movies/The Matrix (1999)/movie.mkv")

        mock_config = MagicMock()
        mock_config.general.remote_path_mappings = []

        with patch("wi1_bot.arr.util.config", mock_config):
            result = replace_remote_paths(path)

        assert result == path

    def test_single_mapping_match(self) -> None:
        path = Path("/mnt/remote/movies/The Matrix (1999)/movie.mkv")
        mappings = [RemotePathMapping(remote=Path("/mnt/remote"), local=Path("/local"))]

        mock_config = MagicMock()
        mock_config.general = GeneralConfig(remote_path_mappings=mappings)

        with patch("wi1_bot.arr.util.config", mock_config):
            result = replace_remote_paths(path)

        assert result == Path("/local/movies/The Matrix (1999)/movie.mkv")

    def test_single_mapping_no_match(self) -> None:
        path = Path("/movies/The Matrix (1999)/movie.mkv")
        mappings = [RemotePathMapping(remote=Path("/mnt/remote"), local=Path("/local"))]

        mock_config = MagicMock()
        mock_config.general = GeneralConfig(remote_path_mappings=mappings)

        with patch("wi1_bot.arr.util.config", mock_config):
            result = replace_remote_paths(path)

        assert result == path

    def test_multiple_mappings_most_specific(self) -> None:
        path = Path("/mnt/remote/movies/action/The Matrix (1999)/movie.mkv")
        mappings = [
            RemotePathMapping(remote=Path("/mnt/remote"), local=Path("/local1")),
            RemotePathMapping(remote=Path("/mnt/remote/movies"), local=Path("/local2")),
            RemotePathMapping(remote=Path("/mnt/remote/movies/action"), local=Path("/local3")),
        ]

        mock_config = MagicMock()
        mock_config.general = GeneralConfig(remote_path_mappings=mappings)

        with patch("wi1_bot.arr.util.config", mock_config):
            result = replace_remote_paths(path)

        # Should use the most specific mapping
        assert result == Path("/local3/The Matrix (1999)/movie.mkv")

    def test_multiple_mappings_partial_match(self) -> None:
        path = Path("/mnt/remote/movies/The Matrix (1999)/movie.mkv")
        mappings = [
            RemotePathMapping(remote=Path("/mnt/remote/tv"), local=Path("/local1")),
            RemotePathMapping(remote=Path("/mnt/remote/movies"), local=Path("/local2")),
        ]

        mock_config = MagicMock()
        mock_config.general = GeneralConfig(remote_path_mappings=mappings)

        with patch("wi1_bot.arr.util.config", mock_config):
            result = replace_remote_paths(path)

        assert result == Path("/local2/The Matrix (1999)/movie.mkv")

    def test_windows_to_linux_path(self) -> None:
        # Note: This test might behave differently on Windows vs Linux
        # In practice, pathlib handles platform-specific paths
        path = Path("/mnt/Z/movies/The Matrix (1999)/movie.mkv")
        mappings = [RemotePathMapping(remote=Path("/mnt/Z"), local=Path("/data"))]

        mock_config = MagicMock()
        mock_config.general = GeneralConfig(remote_path_mappings=mappings)

        with patch("wi1_bot.arr.util.config", mock_config):
            result = replace_remote_paths(path)

        assert result == Path("/data/movies/The Matrix (1999)/movie.mkv")


class TestConfigLoading:
    def test_config_from_env_variable(self, tmp_path: Any) -> None:
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(
            """
radarr:
  url: http://localhost:7878
  api_key: test-radarr-key
  root_folder: /movies
sonarr:
  url: http://localhost:8989
  api_key: test-sonarr-key
  root_folder: /tv
discord:
  bot_token: test-discord-token
  channel_id: 123456789
  admin_id: 987654321
"""
        )

        with patch.dict("os.environ", {"WB_CONFIG_PATH": str(config_file)}):
            # Need to reload the config module to pick up the new env var
            import importlib

            import wi1_bot.config

            importlib.reload(wi1_bot.config)
            config = wi1_bot.config.config

            assert str(config.radarr.url) == "http://localhost:7878/"
            assert config.radarr.api_key == "test-radarr-key"
            assert str(config.sonarr.url) == "http://localhost:8989/"
            assert config.discord.channel_id == 123456789

    def test_config_with_optional_fields(self, tmp_path: Any) -> None:
        config_file = tmp_path / "test_config.yaml"
        config_file.write_text(
            """
radarr:
  url: http://localhost:7878
  api_key: test-radarr-key
  root_folder: /movies
sonarr:
  url: http://localhost:8989
  api_key: test-sonarr-key
  root_folder: /tv
discord:
  bot_token: test-discord-token
  channel_id: 123456789
  admin_id: 987654321
  bot_presence: "Watching movies"
  quotas:
    123456: 100.5
    789012: 200.0
pushover:
  user_key: test-user-key
  api_key: test-api-key
  devices: device1,device2
transcoding:
  hwaccel: cuda
  profiles:
    good:
      video_params: "-c:v libx265"
      audio_params: "-c:a aac"
      languages: "eng,ita"
general:
  remote_path_mappings:
    - remote: /mnt/remote
      local: /local
"""
        )

        with patch.dict("os.environ", {"WB_CONFIG_PATH": str(config_file)}):
            import importlib

            import wi1_bot.config

            importlib.reload(wi1_bot.config)
            config = wi1_bot.config.config

            assert config.discord.bot_presence == "Watching movies"
            assert config.discord.quotas[123456] == 100.5
            assert config.pushover is not None
            assert config.pushover.user_key == "test-user-key"
            assert config.transcoding is not None
            assert config.transcoding.hwaccel == "cuda"
            assert len(config.general.remote_path_mappings) == 1
