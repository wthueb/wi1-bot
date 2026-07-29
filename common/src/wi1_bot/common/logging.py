import logging
import logging.config
import os
from pathlib import Path
from typing import Any, Literal

import structlog
from structlog.contextvars import merge_contextvars
from structlog.processors import CallsiteParameter, CallsiteParameterAdder
from structlog.typing import EventDict, Processor, WrappedLogger


def _normalize_fields(
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    event_dict["level"] = str(event_dict["level"]).upper()
    event_dict["src"] = f"{event_dict.pop('func_name')}:{event_dict.pop('lineno')}"

    if "exception" in event_dict:
        event_dict["exc_info"] = event_dict.pop("exception")

    # ContextVar iteration order is not guaranteed. Keep the historical feed
    # field order so existing logfmt consumers see byte-compatible records.
    feed_context = {
        key: event_dict.pop(key) for key in ("job_id", "worker_id") if key in event_dict
    }
    event_dict.update(feed_context)

    return event_dict


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

    shared_processors: list[Processor] = [
        merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(
            fmt="%Y-%m-%d %H:%M:%S",
            utc=False,
            key="ts",
        ),
        CallsiteParameterAdder(
            [
                CallsiteParameter.FUNC_NAME,
                CallsiteParameter.LINENO,
            ]
        ),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        _normalize_fields,
        structlog.processors.EventRenamer("msg"),
    ]

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=False,
    )

    renderers: dict[str, Processor] = {
        "logfmt": structlog.processors.LogfmtRenderer(
            key_order=["ts", "level", "logger", "src", "msg"],
            drop_missing=True,
            bool_as_flag=False,
        ),
        "json": structlog.processors.JSONRenderer(),
    }

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
        log_dir.mkdir(parents=True, exist_ok=True)

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
            output_format: {
                "()": structlog.stdlib.ProcessorFormatter,
                "foreign_pre_chain": shared_processors,
                "processors": [
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    renderer,
                ],
            }
            for output_format, renderer in renderers.items()
        },
        "handlers": handlers,
        "loggers": {
            "": {"level": "DEBUG", "handlers": root_handlers},
            "wi1_bot": {"level": "DEBUG", "handlers": [], "propagate": True},
            "alembic": {"level": "DEBUG", "handlers": [], "propagate": True},
        },
    }

    logging.config.dictConfig(logging_config)
