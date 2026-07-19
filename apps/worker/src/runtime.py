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

from src.db.session import get_session_factory
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
            runner.run_job(job.id)
            return True

    def run_forever(self) -> None:
        logger.info("worker_started", extra={"worker_id": self.worker_id, "redis_enabled": self.broker is not None})
        if self.broker is not None:
            self.broker.ping()
        try:
            session_factory = get_session_factory()
            with session_factory() as db:
                released = JobRunner(db, handlers=self.handlers).release_orphaned_locks(self.worker_id)
                if released:
                    logger.warning(
                        "worker_released_orphan_locks",
                        extra={"worker_id": self.worker_id, "count": released},
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
                did_work = self.run_once(message)
            except Exception:
                logger.exception("worker_run_once_failed", extra={"worker_id": self.worker_id})
                did_work = False
            if not did_work and self.broker is None:
                time.sleep(self.poll_interval_seconds)
        logger.info("worker_stopped", extra={"worker_id": self.worker_id})
