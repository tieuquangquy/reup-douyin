"""Refuse heavy media work when the volume is nearly full.

ffmpeg does not fail politely on a full disk: the render finishes with a truncated file that
looks like a success. Every clip also leaves behind stems, frames, wavs and intermediate
renders, so a long unattended batch fills a drive quietly. Checking headroom before a heavy
job starts turns a corrupt output into a clear, retryable wait.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
import shutil

from src.enums import JobType

logger = logging.getLogger(__name__)

GIGABYTE = 1024**3
DEFAULT_MIN_FREE_GB = 10

# Stages that write video, audio or frame dumps to the storage root.
DISK_HEAVY_JOB_TYPES: frozenset[str] = frozenset(
    {
        JobType.DOWNLOAD_VIDEO.value,
        JobType.ANALYZE_AUDIO.value,
        JobType.SYNTHESIZE_TTS.value,
        JobType.ANALYZE_OCR.value,
        JobType.RENDER_PREVIEW.value,
        JobType.RENDER_FINAL.value,
    }
)


@dataclass(frozen=True)
class DiskSpaceStatus:
    ok: bool
    free_bytes: int
    required_bytes: int
    message: str | None


def min_free_bytes(settings: object | None = None) -> int:
    """Required headroom in bytes; 0 disables the guard."""
    if settings is None:
        from src.core.settings import get_settings

        settings = get_settings()
    raw = getattr(settings, "min_free_disk_gb", DEFAULT_MIN_FREE_GB)
    try:
        gigabytes = float(raw)
    except (TypeError, ValueError):
        gigabytes = DEFAULT_MIN_FREE_GB
    return max(0, int(gigabytes * GIGABYTE))


def check_disk_headroom(path: str, *, required_bytes: int) -> DiskSpaceStatus:
    if required_bytes <= 0:
        return DiskSpaceStatus(ok=True, free_bytes=0, required_bytes=0, message=None)
    try:
        usage = shutil.disk_usage(path)
    except OSError:
        # An unmeasurable path is not evidence of a full disk; never block on it.
        logger.warning("disk_guard_unreadable_path", extra={"path": path})
        return DiskSpaceStatus(ok=True, free_bytes=0, required_bytes=required_bytes, message=None)

    free = int(usage.free)
    if free >= required_bytes:
        return DiskSpaceStatus(ok=True, free_bytes=free, required_bytes=required_bytes, message=None)
    return DiskSpaceStatus(
        ok=False,
        free_bytes=free,
        required_bytes=required_bytes,
        message=(
            f"Only {free / GIGABYTE:.1f} GB free on {path}; "
            f"{required_bytes / GIGABYTE:.1f} GB required before heavy media work."
        ),
    )
