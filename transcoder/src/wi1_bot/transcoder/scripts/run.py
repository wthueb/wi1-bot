import logging

from wi1_bot.common import setup_logging
from wi1_bot.transcoder.config import config
from wi1_bot.transcoder.worker import run


def main() -> None:
    setup_logging(config.general.log_format, name="wi1-bot-transcoder")

    logger = logging.getLogger(__name__)
    logger.info("starting wi1-bot-transcoder worker")

    try:
        run()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
