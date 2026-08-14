from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import redis
from redis.exceptions import RedisError

try:
    from .api_path import ensure_api_src_on_path
except ImportError:  # Allows `python src/main.py` from apps/worker during local dev.
    from api_path import ensure_api_src_on_path

ensure_api_src_on_path()

from src.core.settings import get_settings
from src.db.session import get_session_factory
from src.analytics.services.publication_metric_cadence_service import PublicationMetricCadenceService
from src.services.artifact_retention import sweep_reclaimable_artifacts
from src.downloaders.download_staging import cleanup_stale_staging
from src.services.job_heartbeat import JobHeartbeat
from src.services.job_runner import JobRunner, StepHandlerRegistry

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedisJobMessage:
    job_id: UUID | None = None
    workspace_id: UUID | None = None

    @classmethod
    def from_raw(cls, raw: bytes | str | None) -> "RedisJobMessage":
        if raw is None:
            return cls()
        text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            return cls(job_id=UUID(text))
        return cls(
            job_id=UUID(str(payload["job_id"])) if payload.get("job_id") else None,
            workspace_id=UUID(str(payload["workspace_id"])) if payload.get("workspace_id") else None,
        )


class RedisJobBroker:
    """Redis broker for worker wake-up messages.

    Durable job state remains in PostgreSQL. Redis is the message broker used to
    wake workers and optionally carry a job id. If Redis is empty, the worker
    still scans PostgreSQL so queued jobs remain resumable after broker loss.
    """

    def __init__(self, *, redis_url: str, queue_name: str = "reup-douyin:jobs") -> None:
        self.queue_name = queue_name
        self.client = redis.Redis.from_url(redis_url, decode_responses=False)

    def pop(self, *, timeout_seconds: int) -> RedisJobMessage | None:
        try:
            item = self.client.blpop(self.queue_name, timeout=timeout_seconds)
        except RedisError:
            logger.exception("redis_broker_pop_failed", extra={"queue_name": self.queue_name})
            return None
        if item is None:
            return None
        _, raw = item
        try:
            return RedisJobMessage.from_raw(raw)
        except (TypeError, ValueError):
            logger.warning("redis_broker_invalid_message", extra={"queue_name": self.queue_name})
            return RedisJobMessage()

    def ping(self) -> bool:
        try:
            return bool(self.client.ping())
        except RedisError:
            logger.exception("redis_broker_ping_failed", extra={"queue_name": self.queue_name})
            return False


class LocalPollingWorker:
    def __init__(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float = 5.0,
        handlers: StepHandlerRegistry | None = None,
        redis_url: str | None = None,
        redis_queue_name: str = "reup-douyin:jobs",
    ):
        self.worker_id = worker_id
        self.poll_interval_seconds = poll_interval_seconds
        self.handlers = handlers
        self.broker = RedisJobBroker(redis_url=redis_url, queue_name=redis_queue_name) if redis_url else None
        self._stop_requested = False
        self._last_artifact_sweep_at: float | None = None
        self._last_metric_schedule_sweep_at: float | None = None

    def stop(self) -> None:
        self._stop_requested = True

    def run_once(self, message: RedisJobMessage | None = None) -> bool:
        session_factory = get_session_factory()
        with session_factory() as db:
            runner = JobRunner(db, handlers=self.handlers)
            if message and message.job_id:
                logger.info(
                    "redis_broker_job_message_received",
                    extra={"job_id": str(message.job_id), "worker_id": self.worker_id},
                )
            job = runner.claim_next_job(self.worker_id)
            if job is None:
                return False
            # Long media steps (render, OCR) must refresh their lock, otherwise the stale
            # sweeper judges them by wall clock since claim and requeues healthy work.
            with JobHeartbeat(
                session_factory=session_factory,
                job_id=job.id,
                worker_id=self.worker_id,
                interval_seconds=float(getattr(get_settings(), "job_heartbeat_seconds", 30) or 30),
            ):
                runner.run_job(job.id)
            return True

    def maybe_sweep_artifacts(self, *, now: float | None = None, interval_seconds: float | None = None) -> None:
        """Reclaim finished clips' intermediates on a slow clock.

        Housekeeping touches the filesystem, so it runs on its own interval rather than on
        every poll, and a failure here must never disturb job execution.
        """
        now = time.monotonic() if now is None else now
        if interval_seconds is None:
            interval_seconds = float(getattr(get_settings(), "artifact_retention_sweep_interval_seconds", 900) or 900)
        last = self._last_artifact_sweep_at
        if last is not None and (now - last) < interval_seconds:
            return
        self._last_artifact_sweep_at = now
        try:
            staging_freed = cleanup_stale_staging(
                ttl_seconds=float(getattr(get_settings(), "douyin_download_staging_ttl_hours", 24.0) or 24.0) * 3600
            )
            if staging_freed:
                logger.info(
                    "worker_reclaimed_download_staging",
                    extra={"worker_id": self.worker_id, "bytes_reclaimed": staging_freed},
                )
            with get_session_factory()() as db:
                freed = sweep_reclaimable_artifacts(db)
            if freed:
                logger.info(
                    "worker_reclaimed_artifacts",
                    extra={"worker_id": self.worker_id, "bytes_reclaimed": freed},
                )
        except Exception:
            logger.exception("worker_artifact_sweep_failed", extra={"worker_id": self.worker_id})

    def maybe_dispatch_metric_schedules(
        self,
        *,
        now: float | None = None,
        interval_seconds: float | None = None,
    ) -> None:
        settings = get_settings()
        if not bool(getattr(settings, "metrics_scheduler_enabled", False)):
            return
        now = time.monotonic() if now is None else now
        if interval_seconds is None:
            interval_seconds = float(
                getattr(settings, "metrics_scheduler_sweep_interval_seconds", 60) or 60
            )
        last = self._last_metric_schedule_sweep_at
        if last is not None and (now - last) < interval_seconds:
            return
        self._last_metric_schedule_sweep_at = now
        try:
            with get_session_factory()() as db:
                summary = PublicationMetricCadenceService(db).dispatch_due(
                    limit=max(1, int(getattr(settings, "metrics_scheduler_dispatch_limit", 20) or 20))
                )
            if summary["evaluated_count"]:
                logger.info(
                    "worker_metric_schedules_dispatched",
                    extra={"worker_id": self.worker_id, **summary},
                )
        except Exception:
            logger.exception(
                "worker_metric_schedule_dispatch_failed",
                extra={"worker_id": self.worker_id},
            )

    def _release_locks_after_failure(self, exc: Exception) -> None:
        try:
            with get_session_factory()() as db:
                released = JobRunner(
                    db, handlers=self.handlers
                ).release_failed_execution_locks(
                    self.worker_id,
                    error_type=type(exc).__name__,
                )
            if released:
                logger.warning(
                    "worker_released_locks_after_failure",
                    extra={"worker_id": self.worker_id, "count": released},
                )
        except Exception:
            logger.exception(
                "worker_release_locks_after_failure_failed",
                extra={"worker_id": self.worker_id},
            )

    def run_forever(self) -> None:
        logger.info("worker_started", extra={"worker_id": self.worker_id, "redis_enabled": self.broker is not None})
        if self.broker is not None:
            self.broker.ping()
        try:
            session_factory = get_session_factory()
            with session_factory() as db:
                runner = JobRunner(db, handlers=self.handlers)
                released = runner.release_orphaned_locks(self.worker_id)
                if released:
                    logger.warning(
                        "worker_released_orphan_locks",
                        extra={"worker_id": self.worker_id, "count": released},
                    )
                stale = runner.release_stale_running_locks()
                if stale:
                    logger.warning(
                        "worker_released_stale_locks",
                        extra={"worker_id": self.worker_id, "count": stale},
                    )
        except Exception:
            logger.exception(
                "worker_release_orphan_locks_failed",
                extra={"worker_id": self.worker_id},
            )
        while not self._stop_requested:
            message = None
            if self.broker is not None:
                message = self.broker.pop(timeout_seconds=max(1, int(self.poll_interval_seconds)))
            try:
                # Reclaim hung downloads (e.g. register_assets stuck at ~71%) before claim.
                try:
                    with get_session_factory()() as db:
                        stale = JobRunner(db, handlers=self.handlers).release_stale_running_locks()
                        if stale:
                            logger.warning(
                                "worker_released_stale_locks",
                                extra={"worker_id": self.worker_id, "count": stale},
                            )
                except Exception:
                    logger.exception(
                        "worker_release_stale_locks_failed",
                        extra={"worker_id": self.worker_id},
                    )
                self.maybe_sweep_artifacts()
                self.maybe_dispatch_metric_schedules()
                did_work = self.run_once(message)
            except Exception as exc:
                logger.exception("worker_run_once_failed", extra={"worker_id": self.worker_id})
                did_work = False
                # The job this worker was executing is still RUNNING in the database.
                # Requeue it now without claiming that the still-live worker restarted.
                self._release_locks_after_failure(exc)
            if not did_work and self.broker is None:
                time.sleep(self.poll_interval_seconds)
        logger.info("worker_stopped", extra={"worker_id": self.worker_id})
