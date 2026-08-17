from __future__ import annotations

from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
from typing import BinaryIO, Iterator


class WorkerInstanceLockError(RuntimeError):
    """Raised when another local process already owns a worker identity."""


def _lock_directory() -> Path:
    configured = str(os.getenv("WORKER_LOCK_DIR") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[3] / ".dev" / "worker-locks"


def _safe_worker_name(worker_id: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(worker_id).strip())
    return normalized[:120] or "worker"


def _acquire(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(handle: BinaryIO) -> None:
    handle.seek(0)
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return
    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def worker_instance_lock(
    worker_id: str,
    *,
    lock_dir: Path | None = None,
) -> Iterator[Path]:
    """Hold an OS lock for one stable worker id for the process lifetime.

    Two polling processes sharing ``local-worker-1`` can otherwise release each
    other's recovery locks and, during an upgrade, an old process can still
    claim a new job. The kernel releases this lock automatically after a crash.
    """

    directory = (lock_dir or _lock_directory()).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{_safe_worker_name(worker_id)}.lock"
    handle = path.open("a+b")
    acquired = False
    try:
        if path.stat().st_size == 0:
            handle.write(b"\0")
            handle.flush()
        try:
            _acquire(handle)
            acquired = True
        except OSError as exc:
            raise WorkerInstanceLockError(
                f"Worker identity is already active: {worker_id}"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {"worker_id": str(worker_id), "pid": os.getpid()},
                sort_keys=True,
            ).encode("utf-8")
        )
        handle.flush()
        yield path
    finally:
        if acquired:
            try:
                _release(handle)
            except OSError:
                pass
        handle.close()
