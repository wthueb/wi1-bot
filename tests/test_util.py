import pathlib
from unittest.mock import patch

from wi1_bot.arr.util import replace_remote_paths


class TestReplaceRemotePaths:
    def test_no_config(self):
        path = pathlib.Path("/movies/The Matrix (1999)/movie.mkv")

        with patch("wi1_bot.arr.util.config", {}):
            result = replace_remote_paths(path)

        assert result == path

    def test_no_mappings(self):
        path = pathlib.Path("/movies/The Matrix (1999)/movie.mkv")

        with patch("wi1_bot.arr.util.config", {"general": {}}):
            result = replace_remote_paths(path)

        assert result == path

    def test_single_mapping_match(self):
        path = pathlib.Path("/mnt/remote/movies/The Matrix (1999)/movie.mkv")
        mappings = [{"remote": "/mnt/remote", "local": "/local"}]

        with patch("wi1_bot.arr.util.config", {"general": {"remote_path_mappings": mappings}}):
            result = replace_remote_paths(path)

        assert result == pathlib.Path("/local/movies/The Matrix (1999)/movie.mkv")

    def test_single_mapping_no_match(self):
        path = pathlib.Path("/movies/The Matrix (1999)/movie.mkv")
        mappings = [{"remote": "/mnt/remote", "local": "/local"}]

        with patch("wi1_bot.arr.util.config", {"general": {"remote_path_mappings": mappings}}):
            result = replace_remote_paths(path)

        assert result == path

    def test_multiple_mappings_most_specific(self):
        path = pathlib.Path("/mnt/remote/movies/action/The Matrix (1999)/movie.mkv")
        mappings = [
            {"remote": "/mnt/remote", "local": "/local1"},
            {"remote": "/mnt/remote/movies", "local": "/local2"},
            {"remote": "/mnt/remote/movies/action", "local": "/local3"},
        ]

        with patch("wi1_bot.arr.util.config", {"general": {"remote_path_mappings": mappings}}):
            result = replace_remote_paths(path)

        # Should use the most specific mapping
        assert result == pathlib.Path("/local3/The Matrix (1999)/movie.mkv")

    def test_multiple_mappings_partial_match(self):
        path = pathlib.Path("/mnt/remote/movies/The Matrix (1999)/movie.mkv")
        mappings = [
            {"remote": "/mnt/remote/tv", "local": "/local1"},
            {"remote": "/mnt/remote/movies", "local": "/local2"},
        ]

        with patch("wi1_bot.arr.util.config", {"general": {"remote_path_mappings": mappings}}):
            result = replace_remote_paths(path)

        assert result == pathlib.Path("/local2/The Matrix (1999)/movie.mkv")

    def test_windows_to_linux_path(self):
        # Note: This test might behave differently on Windows vs Linux
        # In practice, pathlib handles platform-specific paths
        path = pathlib.Path("/mnt/Z/movies/The Matrix (1999)/movie.mkv")
        mappings = [{"remote": "/mnt/Z", "local": "/data"}]

        with patch("wi1_bot.arr.util.config", {"general": {"remote_path_mappings": mappings}}):
            result = replace_remote_paths(path)

        assert result == pathlib.Path("/data/movies/The Matrix (1999)/movie.mkv")


class TestConfigLoading:
    def test_config_from_env_variable(self, tmp_path):
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

            assert config["radarr"]["url"] == "http://localhost:7878"
            assert config["radarr"]["api_key"] == "test-radarr-key"
            assert config["sonarr"]["url"] == "http://localhost:8989"
            assert config["discord"]["channel_id"] == 123456789

    def test_config_with_optional_fields(self, tmp_path):
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

            assert config["discord"]["bot_presence"] == "Watching movies"  # type: ignore
            assert config["discord"]["quotas"][123456] == 100.5  # type: ignore
            assert config["pushover"]["user_key"] == "test-user-key"  # type: ignore
            assert config["transcoding"]["hwaccel"] == "cuda"  # type: ignore
            assert len(config["general"]["remote_path_mappings"]) == 1  # type: ignore
