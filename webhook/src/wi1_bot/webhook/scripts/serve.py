import structlog
from waitress import serve

from wi1_bot.common import setup_logging
from wi1_bot.webhook import __version__
from wi1_bot.webhook.app import app, autobrr_targets
from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_db_path, init_db
from wi1_bot.webhook.queue_cleanup import ArrQueueCleanupWorker


def main() -> None:
    setup_logging(config.general.log_format, name="wi1-bot-webhook")

    logger = structlog.get_logger(__name__)

    logger.info("starting wi1-bot-webhook", version=__version__)

    db_path = get_db_path()
    logger.info("running database migrations", database_path=str(db_path))
    init_db()
    logger.info("database initialized and migrations complete")

    cleanup_worker: ArrQueueCleanupWorker | None = None
    if config.webhook.queue_cleanup.enabled:
        cleanup_worker = ArrQueueCleanupWorker(
            autobrr_targets,
            config.webhook.queue_cleanup.poll_interval,
        )
        cleanup_worker.start()
        logger.info(
            "arr queue cleanup worker started",
            poll_interval=config.webhook.queue_cleanup.poll_interval,
        )

    try:
        logger.info("starting webhook and job API", port=config.webhook.port)
        serve(app, host="0.0.0.0", port=config.webhook.port)
    finally:
        if cleanup_worker is not None:
            cleanup_worker.stop()


if __name__ == "__main__":
    main()
