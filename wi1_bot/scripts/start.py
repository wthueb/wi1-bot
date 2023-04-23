import asyncio
import logging
import logging.config
import pathlib
from typing import Any

from wi1_bot import webhook
from wi1_bot.config import config
from wi1_bot.discord import bot
from wi1_bot.transcoder import Transcoder


def main() -> None:
    logging_config: dict[str, Any] = {
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
        },
        "loggers": {
            "": {"level": "DEBUG", "handlers": ["console"]},
            "wi1_bot": {"level": "DEBUG", "handlers": [], "propagate": True},
        },
    }

    if "general" in config and "log_dir" in config["general"]:
        log_dir = pathlib.Path(config["general"]["log_dir"]).resolve()

        logging_config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / "wi1-bot.log"),
            "maxBytes": 1024**2 * 10,  # 10 MB
            "backupCount": 20,
            "level": "INFO",
            "formatter": "basic",
        }

        logging_config["handlers"]["file_debug"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / "wi1-bot.debug.log"),
            "maxBytes": 1024**2 * 10,  # 10 MB
            "backupCount": 20,
            "level": "DEBUG",
            "formatter": "detailed",
        }

        logging_config["loggers"][""]["handlers"].extend(["file", "file_debug"])

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
