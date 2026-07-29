import structlog
from waitress import serve

from wi1_bot.common import setup_logging
from wi1_bot.webhook import __version__
from wi1_bot.webhook.app import app
from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_db_path, init_db


def main() -> None:
    setup_logging(config.general.log_format, name="wi1-bot-webhook")

    logger = structlog.get_logger(__name__)

    logger.info("starting wi1-bot-webhook", version=__version__)

    db_path = get_db_path()
    logger.info("running database migrations", database_path=str(db_path))
    init_db()
    logger.info("database initialized and migrations complete")

    logger.info("starting webhook and job API", port=config.webhook.port)
    serve(app, host="0.0.0.0", port=config.webhook.port)


if __name__ == "__main__":
    main()
