import logging
import logging.config
import logging.handlers
import multiprocessing
import threading

import arr_webhook
import bot


def logger_thread(q):
    while True:
        record = q.get()

        if record is None:
            break

        logger = logging.getLogger(record.name)

        logger.handle(record)


if __name__ == '__main__':
    logging_config = {
        'version': 1,

        'disable_existing_loggers': True,

        'formatters': {
            'detailed': {
                'class': 'logging.Formatter',
                'format': '[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s'
            }
        },

        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'stream': 'ext://sys.stdout',
                'level': 'DEBUG',
                'formatter': 'detailed'
            },
            'file': {
                'class': 'logging.handlers.RotatingFileHandler',
                'filename': 'logs/wi1-bot.log',
                'maxBytes': 1024**2 * 10,  # 10 MB
                'backupCount': 20,
                'level': 'INFO',
                'formatter': 'detailed'
            }
        },

        'loggers': {
            'wi1-bot': {
                'handlers': ['console', 'file'],
                'propagate': False
            }
        }
    }

    logging.config.dictConfig(logging_config)

    logging_queue = multiprocessing.Queue()

    webhook_worker = multiprocessing.Process(target=arr_webhook.run, args=(logging_queue,))
    webhook_worker.start()

    bot_worker = multiprocessing.Process(target=bot.run, args=(logging_queue,))
    bot_worker.start()

    logging_thread = threading.Thread(target=logger_thread, args=(logging_queue,))
    logging_thread.start()

    webhook_worker.join()
    bot_worker.join()

    logging_queue.put(None)
    logging_thread.join()
