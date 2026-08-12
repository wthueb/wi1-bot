import pytest
from pydantic import ValidationError

from wi1_bot.webhook.config import Config, QueueCleanupConfig, WebhookConfig


def test_queue_cleanup_is_opt_in_with_sixty_second_default() -> None:
    cleanup = WebhookConfig().queue_cleanup

    assert cleanup.enabled is False
    assert cleanup.poll_interval == 60


def test_queue_cleanup_accepts_enabled_custom_interval() -> None:
    cleanup = QueueCleanupConfig(enabled=True, poll_interval=5)

    assert cleanup.enabled is True
    assert cleanup.poll_interval == 5


def test_queue_cleanup_supports_nested_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WB_WEBHOOK__QUEUE_CLEANUP__ENABLED", "true")
    monkeypatch.setenv("WB_WEBHOOK__QUEUE_CLEANUP__POLL_INTERVAL", "12.5")

    cleanup = Config().webhook.queue_cleanup

    assert cleanup.enabled is True
    assert cleanup.poll_interval == 12.5


@pytest.mark.parametrize("poll_interval", [0, -1])
def test_queue_cleanup_rejects_non_positive_interval(poll_interval: float) -> None:
    with pytest.raises(ValidationError):
        QueueCleanupConfig(poll_interval=poll_interval)
