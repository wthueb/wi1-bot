from pathlib import Path

import pytest
from pydantic import ValidationError

from wi1_bot.webhook.config import Config, IMDbPopularListConfig, QueueCleanupConfig, WebhookConfig


def test_queue_cleanup_is_opt_in_with_sixty_second_default() -> None:
    cleanup = WebhookConfig().queue_cleanup

    assert cleanup.enabled is False
    assert cleanup.manually_added is False
    assert cleanup.poll_interval == 60


@pytest.mark.parametrize("manually_added", [False, True])
def test_queue_cleanup_accepts_enabled_custom_interval(manually_added: bool) -> None:
    cleanup = QueueCleanupConfig(enabled=True, poll_interval=5, manually_added=manually_added)

    assert cleanup.enabled is True
    assert cleanup.manually_added is manually_added
    assert cleanup.poll_interval == 5


@pytest.mark.parametrize("manually_added", [False, True])
def test_queue_cleanup_supports_nested_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
    manually_added: bool,
) -> None:
    monkeypatch.setenv("WB_WEBHOOK__QUEUE_CLEANUP__ENABLED", "true")
    monkeypatch.setenv("WB_WEBHOOK__QUEUE_CLEANUP__POLL_INTERVAL", "12.5")
    monkeypatch.setenv("WB_WEBHOOK__QUEUE_CLEANUP__MANUALLY_ADDED", str(manually_added).lower())

    cleanup = Config().webhook.queue_cleanup

    assert cleanup.enabled is True
    assert cleanup.manually_added is manually_added
    assert cleanup.poll_interval == 12.5


@pytest.mark.parametrize("manually_added", [False, True])
def test_queue_cleanup_loads_yaml_with_environment_precedence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manually_added: bool
) -> None:
    config_path = tmp_path / "config.yaml"
    base_config = (Path(__file__).parents[2] / "tests" / "config.yaml").read_text()
    config_path.write_text(
        base_config
        + "\nwebhook:\n"
        + "  queue_cleanup:\n"
        + f"    manually_added: {str(manually_added).lower()}\n"
    )
    monkeypatch.setenv("WB_CONFIG_PATH", str(config_path))
    monkeypatch.delenv("WB_WEBHOOK__QUEUE_CLEANUP__MANUALLY_ADDED", raising=False)

    assert Config().webhook.queue_cleanup.manually_added is manually_added

    monkeypatch.setenv("WB_WEBHOOK__QUEUE_CLEANUP__MANUALLY_ADDED", str(not manually_added).lower())
    assert Config().webhook.queue_cleanup.manually_added is not manually_added


@pytest.mark.parametrize("poll_interval", [0, -1])
def test_queue_cleanup_rejects_non_positive_interval(poll_interval: float) -> None:
    with pytest.raises(ValidationError):
        QueueCleanupConfig(poll_interval=poll_interval)


def test_imdb_popular_list_defaults_to_all_languages() -> None:
    filters = WebhookConfig().imdb_popular_list

    assert filters.include_languages == []
    assert filters.exclude_languages == []


def test_imdb_popular_list_normalizes_and_deduplicates_codes() -> None:
    filters = IMDbPopularListConfig(include_languages=[" EN ", "en", "JA"])

    assert filters.include_languages == ["en", "ja"]


@pytest.mark.parametrize("language", ["", "english", "e", "en-US", "1e", "éè"])
def test_imdb_popular_list_rejects_invalid_codes(language: str) -> None:
    with pytest.raises(ValidationError):
        IMDbPopularListConfig(include_languages=[language])


def test_imdb_popular_list_rejects_overlapping_codes() -> None:
    with pytest.raises(ValidationError, match="must not overlap"):
        IMDbPopularListConfig(include_languages=["EN"], exclude_languages=[" en "])


def test_imdb_popular_list_loads_yaml_and_nested_environment_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "radarr:\n"
        "  url: http://localhost:7878\n"
        "  api_key: test\n"
        "  root_folder: /movies\n"
        "  instance_name: Radarr\n"
        "sonarr:\n"
        "  url: http://localhost:8989\n"
        "  api_key: test\n"
        "  root_folder: /shows\n"
        "  instance_name: Sonarr\n"
        "webhook:\n"
        "  imdb_popular_list:\n"
        "    include_languages: [en, ja]\n"
        "    exclude_languages: [fr]\n"
    )
    monkeypatch.setenv("WB_CONFIG_PATH", str(config_path))
    assert Config().webhook.imdb_popular_list.include_languages == ["en", "ja"]

    monkeypatch.setenv("WB_WEBHOOK__IMDB_POPULAR_LIST__INCLUDE_LANGUAGES", '["DE"]')
    filters = Config().webhook.imdb_popular_list
    assert filters.include_languages == ["de"]
    assert filters.exclude_languages == ["fr"]
