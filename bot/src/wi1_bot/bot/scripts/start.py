import asyncio

import structlog

from wi1_bot.bot import __version__
from wi1_bot.bot.config import config
from wi1_bot.bot.db import init_db
from wi1_bot.bot.discord import bot
from wi1_bot.common import setup_logging


def main() -> None:
    setup_logging(config.general.log_format, name="wi1-bot")

    logger = structlog.get_logger(__name__)

    logger.info("starting wi1-bot", version=__version__)

    init_db()

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
