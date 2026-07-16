import asyncio
import logging

from wi1_bot.bot import __version__
from wi1_bot.bot.config import config
from wi1_bot.bot.discord import bot
from wi1_bot.common import setup_logging


def main() -> None:
    setup_logging(config.general.log_format, name="wi1-bot")

    logger = logging.getLogger(__name__)

    logger.info(f"starting wi1-bot version {__version__}")

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
