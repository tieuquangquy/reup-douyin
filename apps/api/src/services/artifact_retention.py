"""Reclaim the intermediates a finished clip no longer needs.

Every localized clip leaves behind separated stems, extracted audio, per-line TTS clips and
OCR frames — all of them regenerable, all of them large. Nothing removed them, so a few
hundred clips fill the volume and the disk guard ends up refusing work on a drive full of
scratch files.

Deleting media is unforgiving, so the policy here is deliberately narrow: only regenerable
types, only for a clip that finished with a real deliverable, only once the files are old
enough that an operator reviewing today still has them, and only when explicitly enabled.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
import logging
from typing import Any, Iterable, Sequence

from sqlalchemy import select

from src.core.settings import get_settings
from src.enums import MediaAssetStatus, MediaAssetType, ReupQueueStatus
from src.services.reup_pipeline_meta import (
    PIPELINE_STEP_READY_FINAL,
    RENDER_QA_KEY,
    get_pipeline_step,
    meta_dict,
)

logger = logging.getLogger(__name__)

DEFAULT_MIN_AGE_HOURS = 24
MIN_AGE_FLOOR = timedelta(hours=1)

# The source and the deliverable. Losing either means the work cannot be redone at all.
PROTECTED_ASSET_TYPES: frozenset[MediaAssetType] = frozenset(
    {
        MediaAssetType.SOURCE_VIDEO_RAW,
        MediaAssetType.SOURCE_VIDEO_PREVIEW,
        MediaAssetType.THUMBNAIL,
        MediaAssetType.FINAL_RENDER_VIDEO,
        MediaAssetType.RENDER_OUTPUT,
    }
)

# Large and regenerable from the source plus the stored transcript/subtitles.
RECLAIMABLE_ASSET_TYPES: frozenset[MediaAssetType] = frozenset(
    {
        MediaAssetType.SOURCE_AUDIO_EXTRACT,
        MediaAssetType.AUDIO_VOCAL_STEM,
        MediaAssetType.AUDIO_BACKGROUND_STEM,
        MediaAssetType.TTS_AUDIO_CLIP,
        MediaAssetType.OCR_FRAME,
        MediaAssetType.TEMP_FILE,
    }
)

# Biggest single win, but some operators re-render from it instead of cleaning again.
OPT_IN_ASSET_TYPES: frozenset[MediaAssetType] = frozenset({MediaAssetType.CLEANED_VIDEO})

DELIVERABLE_ASSET_TYPES: frozenset[MediaAssetType] = frozenset(
    {MediaAssetType.FINAL_RENDER_VIDEO, MediaAssetType.RENDER_OUTPUT}
)

_FINISHED_STATUSES: frozenset[ReupQueueStatus] = frozenset(
    {
        ReupQueueStatus.READY_TO_EXPORT,
        ReupQueueStatus.EXPORT_PACKAGE_CREATED,
        ReupQueueStatus.READY_TO_PUBLISH,
        ReupQueueStatus.PUBLISH_HANDOFF_CREATED,
        ReupQueueStatus.COMPLETED,
    }
)


@dataclass(frozen=True)
class ReclaimPlan:
    assets: list[Any] = field(default_factory=list)
    bytes_reclaimable: int = 0


@dataclass(frozen=True)
class ReclaimResult:
    deleted_count: int = 0
    failed_count: int = 0
    bytes_reclaimed: int = 0


def retention_enabled(settings: object | None = None) -> bool:
    cfg = settings if settings is not None else get_settings()
    return bool(getattr(cfg, "artifact_retention_enabled", False))


def reclaim_min_age(settings: object | None = None) -> timedelta:
    cfg = settings if settings is not None else get_settings()
    try:
        hours = float(getattr(cfg, "artifact_retention_min_age_hours", DEFAULT_MIN_AGE_HOURS))
    except (TypeError, ValueError):
        hours = DEFAULT_MIN_AGE_HOURS
    return max(MIN_AGE_FLOOR, timedelta(hours=hours))


def include_cleaned_video(settings: object | None = None) -> bool:
    cfg = settings if settings is not None else get_settings()
    return bool(getattr(cfg, "artifact_retention_include_cleaned_video", False))


def _asset_type(asset: Any) -> MediaAssetType | None:
    raw = getattr(asset, "asset_type", None)
    if isinstance(raw, MediaAssetType):
        return raw
    try:
        return MediaAssetType(str(raw))
    except ValueError:
        return None


def is_reclaimable_asset(
    asset: Any,
    *,
    now: datetime,
    min_age: timedelta,
    include_cleaned_video: bool = False,
) -> bool:
    asset_type = _asset_type(asset)
    if asset_type is None or asset_type in PROTECTED_ASSET_TYPES:
        return False
    allowed = RECLAIMABLE_ASSET_TYPES | (OPT_IN_ASSET_TYPES if include_cleaned_video else frozenset())
    if asset_type not in allowed:
        return False
    if str(getattr(asset, "status", "")) == str(MediaAssetStatus.ARCHIVED):
        return False
    created = getattr(asset, "created_at", None)
    if created is None:
        return False
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return (now - created) >= min_age


def item_is_finished(item: Any) -> bool:
    """Whether a clip is done with its intermediates.

    A stranded or QA-failed clip keeps everything: the intermediates are the evidence
    somebody needs to work out what went wrong.
    """
    status = getattr(item, "status", None)
    meta = meta_dict(item)
    qa_status = str((meta.get(RENDER_QA_KEY) or {}).get("status") or "").lower()
    if qa_status == "fail":
        return False
    if status in _FINISHED_STATUSES:
        return True
    return status == ReupQueueStatus.COMPLETED and get_pipeline_step(item) == PIPELINE_STEP_READY_FINAL


def plan_reclaim(
    assets: Sequence[Any],
    *,
    now: datetime,
    min_age: timedelta,
    include_cleaned_video: bool = False,
) -> ReclaimPlan:
    has_deliverable = any(_asset_type(asset) in DELIVERABLE_ASSET_TYPES for asset in assets)
    if not has_deliverable:
        return ReclaimPlan()

    reclaimable = [
        asset
        for asset in assets
        if is_reclaimable_asset(asset, now=now, min_age=min_age, include_cleaned_video=include_cleaned_video)
    ]
    total = sum(int(getattr(asset, "size_bytes", 0) or 0) for asset in reclaimable)
    return ReclaimPlan(assets=reclaimable, bytes_reclaimable=total)


def reclaim_item_artifacts(
    db: Any,
    item: Any,
    *,
    storage: Any,
    now: datetime | None = None,
    min_age: timedelta | None = None,
    include_cleaned: bool | None = None,
) -> ReclaimResult:
    """Delete the regenerable artifacts of one finished clip."""
    from src.models.media import MediaAsset

    if not item_is_finished(item):
        return ReclaimResult()

    now = now or datetime.now(UTC)
    min_age = min_age if min_age is not None else reclaim_min_age()
    include = include_cleaned if include_cleaned is not None else include_cleaned_video()

    assets = list(
        db.scalars(select(MediaAsset).where(MediaAsset.source_video_id == getattr(item, "source_video_id", None))).all()
    )
    plan = plan_reclaim(assets, now=now, min_age=min_age, include_cleaned_video=include)
    if not plan.assets:
        return ReclaimResult()

    deleted = 0
    failed = 0
    freed = 0
    for asset in plan.assets:
        key = getattr(asset, "logical_key", None) or getattr(asset, "storage_key", None)
        if not key:
            continue
        try:
            storage.delete(key)
        except FileNotFoundError:
            # The file is already gone; archiving the row is exactly the desired end state.
            pass
        except Exception:  # noqa: BLE001 — a locked file just waits for the next pass
            failed += 1
            logger.warning(
                "artifact_reclaim_delete_failed",
                extra={"asset_id": str(getattr(asset, "id", "")), "logical_key": key},
                exc_info=True,
            )
            continue
        asset.status = MediaAssetStatus.ARCHIVED
        deleted += 1
        freed += int(getattr(asset, "size_bytes", 0) or 0)

    if deleted:
        logger.info(
            "artifact_reclaim_done",
            extra={
                "reup_queue_item_id": str(getattr(item, "id", "")),
                "deleted_count": deleted,
                "bytes_reclaimed": freed,
            },
        )
    return ReclaimResult(deleted_count=deleted, failed_count=failed, bytes_reclaimed=freed)


def finished_items_for_sweep(db: Any, *, limit: int) -> Iterable[Any]:
    from src.models.reup_queue import ReupQueueItem

    return db.scalars(
        select(ReupQueueItem)
        .where(ReupQueueItem.status.in_(tuple(_FINISHED_STATUSES)))
        .order_by(ReupQueueItem.updated_at.asc())
        .limit(limit)
    ).all()


def sweep_reclaimable_artifacts(db: Any, *, storage: Any | None = None, limit: int = 25) -> int:
    """Reclaim artifacts across finished clips. Returns bytes freed."""
    settings = get_settings()
    if not retention_enabled(settings):
        return 0

    if storage is None:
        from src.storage.local import LocalStorageBackend

        storage = LocalStorageBackend(settings.local_storage_root)

    now = datetime.now(UTC)
    min_age = reclaim_min_age(settings)
    include = include_cleaned_video(settings)
    freed = 0
    for item in finished_items_for_sweep(db, limit=limit):
        try:
            result = reclaim_item_artifacts(
                db, item, storage=storage, now=now, min_age=min_age, include_cleaned=include
            )
        except Exception:  # noqa: BLE001 — housekeeping must never break the worker loop
            logger.exception(
                "artifact_reclaim_item_failed",
                extra={"reup_queue_item_id": str(getattr(item, "id", ""))},
            )
            continue
        freed += result.bytes_reclaimed
    if freed:
        db.commit()
    return freed
