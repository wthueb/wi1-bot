from unittest.mock import MagicMock, patch

import pytest

import wi1_bot.webhook.scripts.serve as serve_mod
from wi1_bot.webhook.config import QueueCleanupConfig


@pytest.mark.parametrize("enabled", [False, True])
def test_cleanup_worker_lifecycle_follows_configuration(enabled: bool) -> None:
    cleanup = QueueCleanupConfig(enabled=enabled, poll_interval=5)
    worker = MagicMock()

    with (
        patch.object(serve_mod.config.webhook, "queue_cleanup", cleanup),
        patch.object(serve_mod, "setup_logging"),
        patch.object(serve_mod, "get_db_path"),
        patch.object(serve_mod, "init_db"),
        patch.object(serve_mod, "ArrQueueCleanupWorker", return_value=worker) as worker_cls,
        patch.object(serve_mod, "serve"),
    ):
        serve_mod.main()

    if enabled:
        worker_cls.assert_called_once_with(serve_mod.autobrr_targets, 5)
        worker.start.assert_called_once_with()
        worker.stop.assert_called_once_with()
    else:
        worker_cls.assert_not_called()
