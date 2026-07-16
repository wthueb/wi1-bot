import logging

from waitress import serve

from wi1_bot.common import setup_logging
from wi1_bot.webhook import __version__
from wi1_bot.webhook.app import app
from wi1_bot.webhook.config import config
from wi1_bot.webhook.db import get_db_path, init_db


def main() -> None:
    setup_logging(config.general.log_format, name="wi1-bot-webhook")

    logger = logging.getLogger(__name__)

    logger.info(f"starting wi1-bot-webhook version {__version__}")

    db_path = get_db_path()
    logger.info(f"database path: {db_path}, running migrations if needed...")
    init_db()
    logger.info("database initialized and migrations complete")

    logger.info(f"starting webhook + job API on port {config.webhook.port}")
    serve(app, host="0.0.0.0", port=config.webhook.port)


if __name__ == "__main__":
    main()
