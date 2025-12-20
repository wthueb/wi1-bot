import asyncio
import logging
import logging.config
import os
from pathlib import Path
from typing import Any

from wi1_bot import __version__, webhook
from wi1_bot.db import get_db_path, init_db
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
                    "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s"
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
            "alembic": {"level": "DEBUG", "handlers": [], "propagate": True},
        },
    }

    log_dir: Path | None = None

    if log_dir_str := os.getenv("WB_LOG_DIR"):
        log_dir = Path(log_dir_str).resolve()

        logging_config["handlers"]["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / "wi1-bot.log"),
            "maxBytes": 1024**2 * 10,  # 10 MB
            "backupCount": 100,
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

    logger = logging.getLogger(__name__)

    logger.info(f"starting wi1-bot version {__version__}")
    logger.info(f"logging to: {log_dir}")

    db_path = get_db_path()
    logger.info(f"database path: {db_path}, running migrations if needed...")
    init_db()
    logger.info("database initialized and migrations complete")

    webhook.start()

    t = Transcoder()
    t.start()

    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
