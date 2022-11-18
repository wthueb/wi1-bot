import asyncio
import logging
import logging.config

from wi1_bot import webhook
from wi1_bot.discord import bot
from wi1_bot.transcoder import Transcoder


def main():
    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "basic": {
                "class": "logging.Formatter",
                "format": "[%(asctime)s] %(levelname)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "detailed": {
                "class": "logging.Formatter",
                "format": (
                    "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d]"
                    " %(message)s"
                ),
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "level": "DEBUG",
                "formatter": "detailed",
            },
            # "file": {
            #     "class": "logging.handlers.RotatingFileHandler",
            #     "filename": "logs/wi1-bot.log",
            #     "maxBytes": 1024**2 * 10,  # 10 MB
            #     "backupCount": 20,
            #     "level": "INFO",
            #     "formatter": "basic",
            # },
            # "file_debug": {
            #     "class": "logging.handlers.RotatingFileHandler",
            #     "filename": "logs/wi1-bot.debug.log",
            #     "maxBytes": 1024**2 * 10,  # 10 MB
            #     "backupCount": 20,
            #     "level": "DEBUG",
            #     "formatter": "detailed",
            # },
        },
        "loggers": {
            "": {"level": "DEBUG", "handlers": ["console"]},
            "wi1_bot": {"level": "DEBUG", "handlers": [], "propagate": True},
            "websockets": {"level": "INFO", "handlers": [], "propagate": True},
        },
    }

    logging.config.dictConfig(logging_config)

    webhook.start()

    t = Transcoder()
    t.start()

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
