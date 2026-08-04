"""Sync DOWNLOAD_VIDEO job outcomes back onto linked Reup Queue items."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import JobStatus, JobType, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.models.reup_queue import ReupQueueItem

logger = logging.getLogger(__name__)

DOWNLOAD_JOB_COMPLETED_METADATA_KEY = "download_job_completed"

_ACTIVE_DOWNLOAD_QUEUE_STATUSES = {
    ReupQueueStatus.WAITING_FOR_MEDIA,
    ReupQueueStatus.PROCESSING,
}


def sync_reup_queue_from_download_job(db: Session, job: Any) -> int:
    """Reflect download job completion/failure onto linked Reup Queue rows.

    Success keeps WAITING_FOR_MEDIA (operator still confirms via MARK_MEDIA_READY)
    but stamps metadata so UI can primary "Mark media ready".

    Final FAILED moves items to FAILED_NEEDS_ATTENTION with safe job error context.
    RETRYABLE and other statuses are ignored (download may resume).
    """
    job_type = getattr(job, "job_type", None)
    if str(job_type) != str(JobType.DOWNLOAD_VIDEO) and job_type != JobType.DOWNLOAD_VIDEO:
        return 0

    job_status = getattr(job, "status", None)
    if job_status not in {JobStatus.COMPLETED, JobStatus.FAILED, str(JobStatus.COMPLETED), str(JobStatus.FAILED)}:
        return 0

    job_id = getattr(job, "id", None)
    if job_id is None:
        return 0

    items = list(
        db.scalars(
            select(ReupQueueItem).where(
                ReupQueueItem.job_id == job_id,
                ReupQueueItem.status.in_(tuple(_ACTIVE_DOWNLOAD_QUEUE_STATUSES)),
            )
        ).unique()
    )
    if not items:
        return 0

    now = datetime.now(UTC)
    updated = 0
    status_value = str(job_status)

    for item in items:
        if status_value == str(JobStatus.COMPLETED):
            _apply_download_success(item, now=now)
            updated += 1
        elif status_value == str(JobStatus.FAILED):
            _apply_download_failure(
                item,
                now=now,
                error_code=getattr(job, "error_code", None),
                error_message=getattr(job, "error_message", None),
            )
            updated += 1

    if updated:
        db.flush()
        logger.info(
            "reup_queue_synced_from_download_job",
            extra={
                "job_id": str(job_id),
                "job_status": status_value,
                "updated_count": updated,
                "reup_queue_item_ids": [str(item.id) for item in items],
            },
        )
    return updated


def is_download_ready_for_confirm(item: ReupQueueItem) -> bool:
    metadata = item.metadata_json or {}
    if metadata.get(DOWNLOAD_JOB_COMPLETED_METADATA_KEY) is True:
        return True
    job = getattr(item, "job", None)
    if job is not None and str(getattr(job, "status", "")) == str(JobStatus.COMPLETED):
        return True
    return False


def next_action_for_item(item: ReupQueueItem) -> str:
    from src.services.reup_pipeline_meta import (
        PIPELINE_STEP_ANALYZE_AUDIO,
        PIPELINE_STEP_DOWNLOAD,
        PIPELINE_STEP_NEEDS_ATTENTION,
        PIPELINE_STEP_OCR,
        PIPELINE_STEP_READY_FINAL,
        PIPELINE_STEP_RENDER,
        PIPELINE_STEP_TRANSLATE,
        PIPELINE_STEP_TTS,
        get_pipeline_step,
        is_auto_pipeline,
        is_pipeline_held,
    )
    from src.services.reup_queue_service import next_action_for_status

    if is_auto_pipeline(item):
        if is_pipeline_held(item):
            return "Auto pipeline paused. Resume to continue, or open Transcript / Final Review to edit."
        step = get_pipeline_step(item)
        if step == PIPELINE_STEP_DOWNLOAD:
            return "Auto pipeline: downloading source media…"
        if step == PIPELINE_STEP_ANALYZE_AUDIO:
            return "Auto pipeline: analyzing audio / transcript…"
        if step == PIPELINE_STEP_TRANSLATE:
            return "Auto pipeline: translating to Vietnamese…"
        if step == PIPELINE_STEP_TTS:
            return "Auto pipeline: generating TTS…"
        if step == PIPELINE_STEP_OCR:
            return "Auto pipeline: analyzing OCR / cleaning hard-sub…"
        if step == PIPELINE_STEP_RENDER:
            return "Auto pipeline: rendering final video…"
        if step == PIPELINE_STEP_READY_FINAL:
            return "Auto pipeline ready for Final Review — open Final to OCR/Render/Compare."
        if step == PIPELINE_STEP_NEEDS_ATTENTION:
            return "Auto pipeline needs attention. Inspect the error, then retry or resume."

    if item.status == ReupQueueStatus.WAITING_FOR_MEDIA and is_download_ready_for_confirm(item):
        return "Source media downloaded. Confirm with Mark media ready, then continue to export."
    return next_action_for_status(item.status)


def _apply_download_success(item: ReupQueueItem, *, now: datetime) -> None:
    metadata = dict(item.metadata_json or {})
    metadata[DOWNLOAD_JOB_COMPLETED_METADATA_KEY] = True
    metadata["download_job_completed_at"] = now.isoformat()
    item.metadata_json = metadata
    item.last_error_code = None
    item.last_error_message = None
    item.failed_at = None
    item.last_action_note = "Download completed. Confirm source media, then mark media ready."


def _apply_download_failure(
    item: ReupQueueItem,
    *,
    now: datetime,
    error_code: str | None,
    error_message: str | None,
) -> None:
    item.status = ReupQueueStatus.FAILED_NEEDS_ATTENTION
    item.media_prep_status = ReupQueueMediaPrepStatus.BLOCKED
    item.failed_at = now
    item.blocked_at = now
    item.blocked_reason = error_message or "Download job failed."
    item.last_error_code = error_code or "DOWNLOAD_JOB_FAILED"
    item.last_error_message = error_message or "Download job failed."
    item.last_action_note = (
        "Download failed. "
        + (
            "Refresh the Douyin download session, then retry."
            if "refresh download session" in (error_message or "").lower() or "auth ·" in (error_message or "").lower()
            else "Inspect the error, then retry or cancel."
        )
    )
    metadata = dict(item.metadata_json or {})
    metadata.pop(DOWNLOAD_JOB_COMPLETED_METADATA_KEY, None)
    metadata.pop("download_job_completed_at", None)
    item.metadata_json = metadata or None
