from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from wi1_bot.arr import Radarr, Sonarr
from wi1_bot.webhook.scripts import transcode_item


def test_resolves_radarr_profile_and_original_language() -> None:
    client = MagicMock(spec=Radarr)
    client.get_root_folders.return_value = [{"path": "/movies"}]
    client.get_movies.return_value = [
        {
            "id": 10,
            "path": "/movies/Perfect Days (2023)",
            "qualityProfileId": 4,
            "originalLanguage": {"id": 8, "name": "Japanese"},
        }
    ]
    client.get_movie_files.return_value = [
        {"id": 20, "path": "/movies/Perfect Days (2023)/Perfect Days.mkv"}
    ]
    client.get_quality_profile_name.return_value = "Bluray-1080p"
    target = transcode_item.MetadataTarget("radarr", "radarr", client)

    metadata = transcode_item.resolve_metadata(
        Path("/movies/Perfect Days (2023)/Perfect Days.mkv"), [target]
    )

    assert metadata == transcode_item.TranscodeMetadata("Bluray-1080p", "Japanese")
    assert client.method_calls == [
        call.get_root_folders(),
        call.get_movies(),
        call.get_movie_files(10),
        call.get_quality_profile_name(4),
    ]


def test_checks_each_root_before_querying_media_files() -> None:
    radarr = MagicMock(spec=Radarr)
    radarr.get_root_folders.return_value = [{"path": "/movies"}]
    sonarr = MagicMock(spec=Sonarr)
    sonarr.get_root_folders.return_value = [{"path": "/tv"}]
    sonarr.get_series.return_value = [
        {
            "id": 30,
            "path": "/tv/Severance",
            "qualityProfileId": 5,
        }
    ]
    sonarr.get_episode_files.return_value = [
        {"id": 40, "path": "/tv/Severance/Season 02/episode.mkv"}
    ]
    sonarr.get_quality_profile_name.return_value = "WEB-2160p"
    targets = [
        transcode_item.MetadataTarget("radarr4k", "radarr", radarr),
        transcode_item.MetadataTarget("sonarr4k", "sonarr", sonarr),
    ]

    metadata = transcode_item.resolve_metadata(Path("/tv/Severance/Season 02/episode.mkv"), targets)

    assert metadata == transcode_item.TranscodeMetadata("WEB-2160p", None)
    radarr.get_movies.assert_not_called()
    radarr.get_movie_files.assert_not_called()
    assert sonarr.method_calls == [
        call.get_root_folders(),
        call.get_series(),
        call.get_episode_files(30),
        call.get_quality_profile_name(5),
    ]


def test_requires_an_exact_arr_file_match() -> None:
    client = MagicMock(spec=Radarr)
    client.get_root_folders.return_value = [{"path": "/movies"}]
    client.get_movies.return_value = [
        {
            "id": 10,
            "path": "/movies/Perfect Days (2023)",
            "qualityProfileId": 4,
        }
    ]
    client.get_movie_files.return_value = [
        {"id": 20, "path": "/movies/Perfect Days (2023)/different.mkv"}
    ]
    target = transcode_item.MetadataTarget("radarr", "radarr", client)

    metadata = transcode_item.resolve_metadata(
        Path("/movies/Perfect Days (2023)/Perfect Days.mkv"), [target]
    )

    assert metadata is None
    client.get_quality_profile_name.assert_not_called()


def test_main_uses_resolved_metadata_and_warns_for_each_fallback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    resolved = transcode_item.TranscodeMetadata("WEB-2160p", "Korean")

    with (
        patch("sys.argv", ["transcode-item", "resolved.mkv", "missing.mkv", "-p", "good"]),
        patch.object(transcode_item, "init_db"),
        patch.object(transcode_item, "_targets_from_config", return_value=[]) as targets,
        patch.object(
            transcode_item,
            "resolve_metadata",
            side_effect=[resolved, None],
        ),
        patch.object(transcode_item, "queue") as queue,
    ):
        transcode_item.main()

    targets.assert_called_once_with()
    assert queue.add.call_args_list == [
        call(
            path=str(Path("resolved.mkv").resolve()),
            quality_profile="WEB-2160p",
            original_language="Korean",
        ),
        call(
            path=str(Path("missing.mkv").resolve()),
            quality_profile="good",
            original_language=None,
        ),
    ]
    captured = capsys.readouterr()
    assert captured.err == (
        f"warning: {Path('missing.mkv').resolve()} not found; using fallback profile 'good' "
        "and no original language\n"
    )
