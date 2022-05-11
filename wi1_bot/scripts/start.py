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
        "root": {"level": "DEBUG", "handlers": ["console"]},
        "loggers": {"wi1-bot": {"handlers": ["file"], "propagate": True}},
    }

    logging_queue: multiprocessing.Queue = multiprocessing.Queue()

    webhook_worker = multiprocessing.Process(target=webhook.run, args=(logging_queue,))
    webhook_worker.start()

    bot_worker = multiprocessing.Process(target=bot.run, args=(logging_queue,))
    bot_worker.start()

    if not os.path.isdir("logs"):
        os.mkdir("logs")

    logging.config.dictConfig(logging_config)

    transcoder.start()

    try:
        while True:
            record = logging_queue.get()

            logger = logging.getLogger(record.name)

            logger.handle(record)
    except KeyboardInterrupt:
        pass

    webhook_worker.terminate()
    bot_worker.terminate()

    webhook_worker.join()
    bot_worker.join()


if __name__ == "__main__":
    main()
