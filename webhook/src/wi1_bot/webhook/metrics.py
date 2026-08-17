import logging
from collections.abc import Iterable
from datetime import datetime, timezone

from prometheus_client import REGISTRY, Counter, Gauge, Histogram, Info
from prometheus_client.core import GaugeMetricFamily, Metric
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from wi1_bot.webhook import __version__
from wi1_bot.webhook.db import get_engine
from wi1_bot.webhook.models import TranscodeItem

logger = logging.getLogger(__name__)

HTTP_REQUESTS = Counter(
    "wi1_bot_webhook_http_requests_total",
    "HTTP requests handled by the webhook.",
    ["method", "route", "status_code"],
)
HTTP_REQUEST_DURATION = Histogram(
    "wi1_bot_webhook_http_request_duration_seconds",
    "Time spent handling webhook HTTP requests.",
    ["method", "route"],
)
HTTP_REQUESTS_IN_PROGRESS = Gauge(
    "wi1_bot_webhook_http_requests_in_progress",
    "Webhook HTTP requests currently being handled.",
    ["method", "route"],
)

EVENTS = Counter(
    "wi1_bot_webhook_events_total",
    "Arr events received by the webhook.",
    ["event_type", "source", "outcome"],
)

QUEUE_CLEANUP_POLLS = Counter(
    "wi1_bot_webhook_queue_cleanup_polls_total",
    "Arr download queue cleanup polls.",
    ["target", "outcome"],
)
QUEUE_CLEANUP_ITEMS = Counter(
    "wi1_bot_webhook_queue_cleanup_items_total",
    "Custom-format downgrade queue cleanup outcomes.",
    ["target", "protocol", "outcome"],
)

JOB_CLAIMS = Counter(
    "wi1_bot_webhook_job_claims_total",
    "Transcode jobs claimed by workers.",
    ["kind"],
)
JOB_HEARTBEATS = Counter(
    "wi1_bot_webhook_job_heartbeats_total",
    "Transcode job lease heartbeats.",
    ["outcome"],
)
JOB_ATTEMPTS = Counter(
    "wi1_bot_webhook_job_attempts_total",
    "Transcode job attempt outcomes.",
    ["outcome"],
)

_JOB_DURATION_BUCKETS = (1, 5, 15, 30, 60, 300, 900, 3600, 21600, 86400)

JOB_QUEUE_WAIT_DURATION = Histogram(
    "wi1_bot_webhook_job_queue_wait_duration_seconds",
    "Time a new or retried transcode job waits to be claimed.",
    ["kind"],
    buckets=_JOB_DURATION_BUCKETS,
)
JOB_ATTEMPT_DURATION = Histogram(
    "wi1_bot_webhook_job_attempt_duration_seconds",
    "Time from a transcode job claim to the end of that attempt.",
    ["outcome"],
    buckets=_JOB_DURATION_BUCKETS,
)

RESCAN_OPERATIONS = Counter(
    "wi1_bot_webhook_rescan_operations_total",
    "Radarr and Sonarr post-transcode rescans.",
    ["target", "outcome"],
)
RESCAN_DURATION = Histogram(
    "wi1_bot_webhook_rescan_duration_seconds",
    "Time spent performing a post-transcode rescan.",
    ["target"],
)
BUILD = Info("wi1_bot_webhook_build", "Webhook build information.")
BUILD.info({"version": __version__})


def elapsed_seconds(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds(), 0.0)


class QueueMetricsCollector:
    @staticmethod
    def _metric_families() -> tuple[
        GaugeMetricFamily,
        GaugeMetricFamily,
        GaugeMetricFamily,
        GaugeMetricFamily,
    ]:
        return (
            GaugeMetricFamily(
                "wi1_bot_webhook_queue_jobs",
                "Current transcode jobs by queue status.",
                labels=["status"],
            ),
            GaugeMetricFamily(
                "wi1_bot_webhook_queue_oldest_job_age_seconds",
                "Age of the oldest transcode job in its current status.",
                labels=["status"],
            ),
            GaugeMetricFamily(
                "wi1_bot_webhook_queue_expired_leases",
                "Transcode jobs with an expired lease.",
            ),
            GaugeMetricFamily(
                "wi1_bot_webhook_database_up",
                "Whether the SQLite transcode queue can be queried.",
            ),
        )

    def describe(self) -> Iterable[Metric]:
        yield from self._metric_families()

    def collect(self) -> Iterable[Metric]:
        jobs, oldest_age, expired_leases, database_up = self._metric_families()

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        counts = {"queued": 0, "in_progress": 0}
        oldest = {"queued": 0.0, "in_progress": 0.0}
        expired = 0

        try:
            with Session(get_engine()) as session:
                status_rows = session.execute(
                    select(
                        TranscodeItem.status,
                        func.count(TranscodeItem.id),
                        func.min(TranscodeItem.status_changed_at),
                    ).group_by(TranscodeItem.status)
                ).all()
                expired = (
                    session.scalar(
                        select(func.count(TranscodeItem.id)).where(
                            TranscodeItem.status == "in_progress",
                            TranscodeItem.lease_expires_at < now,
                        )
                    )
                    or 0
                )

            for status, count, oldest_timestamp in status_rows:
                if status not in counts:
                    continue
                counts[status] = count
                if oldest_timestamp is not None:
                    oldest[status] = elapsed_seconds(oldest_timestamp, now)
            database_up.add_metric([], 1)
        except Exception:
            logger.warning("could not collect webhook queue metrics", exc_info=True)
            database_up.add_metric([], 0)

        for status in ("queued", "in_progress"):
            jobs.add_metric([status], counts[status])
            oldest_age.add_metric([status], oldest[status])
        expired_leases.add_metric([], expired)

        yield jobs
        yield oldest_age
        yield expired_leases
        yield database_up


QUEUE_METRICS_COLLECTOR = QueueMetricsCollector()
REGISTRY.register(QUEUE_METRICS_COLLECTOR)
