import threading
from collections.abc import Iterable

import structlog
from structlog.contextvars import bound_contextvars, clear_contextvars

from wi1_bot.arr import ArrQueueItemNotFound
from wi1_bot.webhook.autobrr import ArrTarget
from wi1_bot.webhook.metrics import QUEUE_CLEANUP_ITEMS, QUEUE_CLEANUP_POLLS

logger = structlog.get_logger(__name__)


class ArrQueueCleanupWorker:
    def __init__(self, targets: Iterable[ArrTarget], poll_interval: float) -> None:
        self._targets = tuple(targets)
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="arr-queue-cleanup",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=30)

    def _run(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            if self._stop.wait(self._poll_interval):
                break

    def run_once(self) -> None:
        clear_contextvars()
        for target in self._targets:
            self._clean_target(target)

    def _clean_target(self, target: ArrTarget) -> None:
        with bound_contextvars(target=target.name):
            try:
                items = target.client.get_queue_items()
            except Exception as exc:
                QUEUE_CLEANUP_POLLS.labels(target=target.name, outcome="error").inc()
                logger.warning(
                    "arr queue cleanup poll failed",
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
                return

            QUEUE_CLEANUP_POLLS.labels(target=target.name, outcome="success").inc()
            logger.debug("arr queue cleanup poll completed", item_count=len(items))

            for item in items:
                if not item.is_custom_format_downgrade:
                    continue

                remove_from_client = item.protocol == "usenet"
                with bound_contextvars(queue_item_id=item.id, protocol=item.protocol):
                    try:
                        target.client.remove_queue_item(
                            item.id,
                            remove_from_client=remove_from_client,
                        )
                    except ArrQueueItemNotFound:
                        outcome = "already_resolved"
                        logger.info("custom format downgrade was already resolved")
                    except Exception as exc:
                        outcome = "error"
                        logger.warning(
                            "custom format downgrade cleanup failed",
                            title=item.title,
                            error_type=type(exc).__name__,
                            exc_info=True,
                        )
                    else:
                        outcome = "removed" if remove_from_client else "ignored"
                        logger.info(
                            "custom format downgrade cleanup completed",
                            title=item.title,
                            action=outcome,
                        )

                    QUEUE_CLEANUP_ITEMS.labels(
                        target=target.name,
                        protocol=item.protocol,
                        outcome=outcome,
                    ).inc()


__all__ = ["ArrQueueCleanupWorker"]
