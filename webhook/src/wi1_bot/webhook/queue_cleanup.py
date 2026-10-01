import threading
from collections.abc import Iterable
from typing import Literal

import structlog
from structlog.contextvars import bound_contextvars, clear_contextvars

from wi1_bot.arr import ArrQueueItemNotFound
from wi1_bot.arr.history import DownloadOrigin
from wi1_bot.webhook.autobrr import ArrTarget
from wi1_bot.webhook.metrics import QUEUE_CLEANUP_ITEMS, QUEUE_CLEANUP_POLLS

logger = structlog.get_logger(__name__)

OriginCheck = DownloadOrigin | Literal["error"]


class ArrQueueCleanupWorker:
    def __init__(
        self,
        targets: Iterable[ArrTarget],
        poll_interval: float,
        *,
        manually_added: bool = False,
    ) -> None:
        self._targets = tuple(targets)
        self._poll_interval = poll_interval
        self._manually_added = manually_added
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

            origins: dict[str, OriginCheck] = {}
            for item in items:
                if not item.is_import_downgrade:
                    continue

                remove_from_client = item.protocol == "usenet"
                with bound_contextvars(queue_item_id=item.id, protocol=item.protocol):
                    if not self._manually_added:
                        origin = self._check_origin(target, item.download_id, origins)
                        if origin != "automatic":
                            outcome = {
                                "manual": "skipped_manual",
                                "unknown": "skipped_unknown",
                                "error": "origin_error",
                            }[origin]
                            logger.debug("import downgrade cleanup skipped", origin=origin)
                            QUEUE_CLEANUP_ITEMS.labels(
                                target=target.name,
                                protocol=item.protocol,
                                outcome=outcome,
                            ).inc()
                            continue

                    try:
                        target.client.remove_queue_item(
                            item.id,
                            remove_from_client=remove_from_client,
                        )
                    except ArrQueueItemNotFound:
                        outcome = "already_resolved"
                        logger.info("import downgrade was already resolved")
                    except Exception as exc:
                        outcome = "error"
                        logger.warning(
                            "import downgrade cleanup failed",
                            title=item.title,
                            error_type=type(exc).__name__,
                            exc_info=True,
                        )
                    else:
                        outcome = "removed" if remove_from_client else "ignored"
                        logger.info(
                            "import downgrade cleanup completed",
                            title=item.title,
                            action=outcome,
                        )

                    QUEUE_CLEANUP_ITEMS.labels(
                        target=target.name,
                        protocol=item.protocol,
                        outcome=outcome,
                    ).inc()

    def _check_origin(
        self,
        target: ArrTarget,
        download_id: str | None,
        origins: dict[str, OriginCheck],
    ) -> OriginCheck:
        if download_id is None or not download_id.strip():
            return "unknown"
        if download_id not in origins:
            try:
                origins[download_id] = target.client.get_download_origin(download_id)
            except Exception as exc:
                origins[download_id] = "error"
                logger.warning(
                    "arr download origin lookup failed",
                    error_type=type(exc).__name__,
                    exc_info=True,
                )
        return origins[download_id]


__all__ = ["ArrQueueCleanupWorker"]
