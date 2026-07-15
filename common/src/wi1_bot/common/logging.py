import logging
import logging.config
import os
from pathlib import Path
from typing import Any, Literal

from pythonjsonlogger.json import JsonFormatter


class SrcJsonFormatter(JsonFormatter):
    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        record.__dict__["src"] = f"{record.funcName}:{record.lineno}"
        super().add_fields(log_data, record, message_dict)


def setup_logging(
    log_format: Literal["logfmt", "json"],
    *,
    name: str = "wi1-bot",
    log_dir: Path | None = None,
) -> None:
    """Configure logging for a wi1-bot service.

    Emits to stdout in ``logfmt`` or ``json``. If ``log_dir`` is given (or the
    ``WB_LOG_DIR`` env var is set), also writes rotating ``{name}.log`` (INFO) and
    ``{name}.debug.log`` (DEBUG) files there so each service keeps its own logs.
    """
    if log_dir is None and (log_dir_str := os.getenv("WB_LOG_DIR")):
        log_dir = Path(log_dir_str).resolve()

    handlers: dict[str, Any] = {
        "console": {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "level": "DEBUG",
            "formatter": log_format,
        },
    }

    root_handlers: list[str] = ["console"]

    if log_dir is not None:
        handlers["file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / f"{name}.log"),
            "maxBytes": 1024**2 * 10,  # 10 MB
            "backupCount": 100,
            "level": "INFO",
            "formatter": log_format,
        }

        handlers["file_debug"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(log_dir / f"{name}.debug.log"),
            "maxBytes": 1024**2 * 10,  # 10 MB
            "backupCount": 20,
            "level": "DEBUG",
            "formatter": log_format,
        }

        root_handlers.extend(["file", "file_debug"])

    logging_config: dict[str, Any] = {
        "version": 1,
        "disable_existing_loggers": True,
        "formatters": {
            "logfmt": {
                "()": "logfmter.Logfmter",
                "keys": ["ts", "level", "logger", "src"],
                "mapping": {
                    "ts": "asctime",
                    "level": "levelname",
                    "logger": "name",
                },
                "defaults": {"src": "{funcName}:{lineno}"},
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "json": {
                "()": SrcJsonFormatter,
                "format": "%(asctime)s %(levelname)s %(name)s %(src)s %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": handlers,
        "loggers": {
            "": {"level": "DEBUG", "handlers": root_handlers},
            "wi1_bot": {"level": "DEBUG", "handlers": [], "propagate": True},
            "alembic": {"level": "DEBUG", "handlers": [], "propagate": True},
        },
    }

    logging.config.dictConfig(logging_config)
