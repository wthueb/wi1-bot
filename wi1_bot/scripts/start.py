import logging
import logging.config
import logging.handlers
import multiprocessing
import os

from wi1_bot import bot, transcoder, webhook


def main():
    logging_config = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "detailed": {
                "class": "logging.Formatter",
                "format": (
                    "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d]"
                    " %(message)s"
                ),
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "stream": "ext://sys.stdout",
                "level": "DEBUG",
                "formatter": "detailed",
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "filename": "logs/wi1-bot.log",
                "maxBytes": 1024**2 * 10,  # 10 MB
                "backupCount": 20,
                "level": "INFO",
                "formatter": "detailed",
            },
        },
        "loggers": {
            "": {"level": "DEBUG", "handlers": ["console"]},
            "wi1-bot": {"handlers": ["file"], "propagate": True},
        },
    }

    if not os.path.isdir("logs"):
        os.mkdir("logs")

    logging.config.dictConfig(logging_config)

    webhook_worker = multiprocessing.Process(target=webhook.run)
    webhook_worker.start()

    transcoder.start()

    try:
        bot.run()
    except KeyboardInterrupt:
        pass
    finally:
        webhook_worker.terminate()
        webhook_worker.join()


if __name__ == "__main__":
    main()
