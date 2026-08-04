from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import shutil
from typing import Any

from src.schemas.operations import OperationalMetricsResponse
from src.schemas.ops_home import OpsHomeDependencySignal, OpsHomeStorageCapacity


_GIB = 1024**3


def probe_operational_dependencies(
    metrics: OperationalMetricsResponse,
    *,
    settings: Any,
    observed_at: datetime | None = None,
) -> tuple[list[OpsHomeDependencySignal], OpsHomeStorageCapacity]:
    """Build fast, local-only dependency signals for Ops Home.

    The probe never calls paid/external providers and never writes a probe file. Signals
    that cannot be proven from the current process are explicitly marked not_observed.
    """

    now = observed_at or datetime.now(UTC)
    backlog = metrics.queue_backlog
    dependencies = [
        OpsHomeDependencySignal(
            key="api",
            label="API",
            state="ready",
            signal="Ops summary request completed",
            impact="Control plane",
            observed_at=now,
            href="/ops/health",
        ),
        OpsHomeDependencySignal(
            key="database",
            label="PostgreSQL",
            state="ready",
            signal="Operational queries completed",
            impact="Durable state",
            observed_at=metrics.generated_at,
            href="/ops/health",
        ),
        _worker_signal(metrics, now),
        OpsHomeDependencySignal(
            key="redis",
            label="Redis broker",
            state="not_observed",
            signal="No canonical broker probe is exposed",
            impact="Queue wake-up",
            observed_at=None,
            href="/ops/health",
        ),
    ]

    capacity = _storage_capacity(settings)
    dependencies.append(
        OpsHomeDependencySignal(
            key="storage",
            label="Local storage",
            state=capacity.state,
            signal=capacity.detail,
            impact="Media and artifacts",
            observed_at=now if capacity.state != "not_observed" else None,
            href="/ops/assets",
        )
    )

    ffmpeg_available = shutil.which("ffmpeg") is not None
    dependencies.append(
        OpsHomeDependencySignal(
            key="ffmpeg",
            label="FFmpeg",
            state="ready" if ffmpeg_available else "critical",
            signal="Binary available on PATH" if ffmpeg_available else "Binary not found on PATH",
            impact="Render and media inspection",
            observed_at=now,
            href="/ops/tools",
        )
    )
    dependencies.append(
        OpsHomeDependencySignal(
            key="providers",
            label="AI providers",
            state="not_observed",
            signal="Live provider probes run only on demand",
            impact="Translation and narration",
            observed_at=None,
            href="/ops/translation-ai",
        )
    )
    return dependencies, capacity


def _worker_signal(metrics: OperationalMetricsResponse, observed_at: datetime) -> OpsHomeDependencySignal:
    backlog = metrics.queue_backlog
    if backlog.running_without_lock > 0:
        state = "critical"
        signal = f"{backlog.running_without_lock} running job(s) have no worker lock"
    elif backlog.running > 0 and backlog.active_worker_count > 0:
        state = "ready"
        signal = f"{backlog.active_worker_count} busy worker signal(s)"
    elif backlog.queued + backlog.retryable > 0:
        state = "warning"
        signal = "Runnable backlog exists with no busy worker signal"
    else:
        state = "not_observed"
        signal = "No idle-worker heartbeat registry"
    return OpsHomeDependencySignal(
        key="worker",
        label="Workers",
        state=state,
        signal=signal,
        impact="Background execution",
        observed_at=observed_at if state != "not_observed" else None,
        href="/ops/jobs",
    )


def _storage_capacity(settings: Any) -> OpsHomeStorageCapacity:
    minimum_free_gb = float(getattr(settings, "min_free_disk_gb", 0) or 0)
    raw_root = str(getattr(settings, "local_storage_root", "") or "").strip()
    if not raw_root:
        return OpsHomeStorageCapacity(minimum_free_gb=minimum_free_gb)
    root = Path(raw_root).expanduser()
    if not root.exists():
        return OpsHomeStorageCapacity(
            minimum_free_gb=minimum_free_gb,
            detail="Storage root is not available yet.",
        )
    try:
        usage = shutil.disk_usage(root)
    except OSError:
        return OpsHomeStorageCapacity(
            minimum_free_gb=minimum_free_gb,
            detail="Storage capacity could not be read.",
        )
    total_gb = usage.total / _GIB
    free_gb = usage.free / _GIB
    used_percent = ((usage.total - usage.free) / usage.total) * 100 if usage.total else 0.0
    if minimum_free_gb > 0 and free_gb < max(1.0, minimum_free_gb / 2):
        state = "critical"
    elif minimum_free_gb > 0 and free_gb < minimum_free_gb:
        state = "warning"
    else:
        state = "ready"
    return OpsHomeStorageCapacity(
        state=state,
        total_gb=round(total_gb, 2),
        free_gb=round(free_gb, 2),
        used_percent=round(used_percent, 1),
        minimum_free_gb=minimum_free_gb,
        detail=f"{free_gb:.1f} GB free of {total_gb:.1f} GB",
    )
