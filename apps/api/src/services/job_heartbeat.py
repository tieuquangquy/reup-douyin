"""Keep a running job's lock warm while a long step executes.

``locked_at`` is stamped once when a worker claims a job, so without a heartbeat the stale
sweeper can only reason about total wall-clock time and cannot tell a 40-minute render
from a dead process. With a heartbeat, "stale" means what it should mean: nobody has
touched this job recently.

The heartbeat runs on its own thread with its own session because the worker's session is
busy inside the step, and it swallows every error: a lost heartbeat must never fail work
that is otherwise succeeding.
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
import logging
import threading
from typing import Any, Callable
from uuid import UUID

from src.enums import JobStatus

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_SECONDS = 30.0


def _status_value(raw: Any) -> str:
    if raw is None:
        return ""
    return raw.value if hasattr(raw, "value") else str(raw)


def touch_job_lock(db: Any, job_id: UUID, *, worker_id: str) -> bool:
    """Refresh ``locked_at`` for a job this worker still owns. Returns whether it beat."""
    from src.models.jobs import Job

    job = db.get(Job, job_id)
    if job is None:
        return False
    if _status_value(getattr(job, "status", None)) != JobStatus.RUNNING.value:
        return False
    if getattr(job, "locked_by", None) != worker_id:
        # Another worker reclaimed it after a stale release; do not steal the lock back.
        return False
    job.locked_at = datetime.now(UTC)
    db.commit()
    return True


class JobHeartbeat(AbstractContextManager["JobHeartbeat"]):
    """Context manager that refreshes a job lock until the block exits."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any],
        job_id: UUID,
        worker_id: str,
        interval_seconds: float = DEFAULT_HEARTBEAT_SECONDS,
    ) -> None:
        self.session_factory = session_factory
        self.job_id = job_id
        self.worker_id = worker_id
        self.interval_seconds = max(0.01, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _beat_once(self) -> None:
        with self.session_factory() as db:
            touch_job_lock(db, self.job_id, worker_id=self.worker_id)

    def _loop(self) -> None:
        while not self._stop.wait(self.interval_seconds):
            try:
                self._beat_once()
            except Exception:
                logger.warning(
                    "job_heartbeat_failed",
                    extra={"job_id": str(self.job_id), "worker_id": self.worker_id},
                    exc_info=True,
                )

    def __enter__(self) -> "JobHeartbeat":
        self._thread = threading.Thread(
            target=self._loop,
            name=f"job-heartbeat-{self.job_id}",
            daemon=True,
        )
        self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=max(1.0, self.interval_seconds))
        self._thread = None
