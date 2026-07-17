from __future__ import annotations

from sqlalchemy import Case, case
from sqlalchemy.sql.elements import ColumnElement

from src.enums import JobStatus, ReupQueueStatus
from src.models.jobs import Job
from src.models.reup_queue import ReupQueueItem

DEFAULT_REUP_QUEUE_SORT = "active_first"

_SORT_ALIASES = {
    "active-first": "active_first",
    "active_first": "active_first",
    "newest": "newest",
    "ready-first": "ready_first",
    "ready_first": "ready_first",
    "needs-attention-first": "needs_attention_first",
    "needs_attention_first": "needs_attention_first",
    "export-ready-first": "export_ready_first",
    "export_ready_first": "export_ready_first",
}


def normalize_reup_queue_sort(value: str | None) -> str:
    if value is None or not str(value).strip():
        return DEFAULT_REUP_QUEUE_SORT
    key = str(value).strip().lower().replace(" ", "_")
    return _SORT_ALIASES.get(key, DEFAULT_REUP_QUEUE_SORT)


def active_first_list_rank(
    *,
    queue_status: ReupQueueStatus | str,
    held_at: bool,
    job_status: JobStatus | str | None,
    blocked: bool,
) -> int:
    """Mirror of SQL CASE used by list_items(sort=active_first). Lower = earlier."""
    status = queue_status.value if isinstance(queue_status, ReupQueueStatus) else str(queue_status)
    job = job_status.value if isinstance(job_status, JobStatus) else (str(job_status) if job_status else None)
    in_flight_queue = status in {
        ReupQueueStatus.WAITING_FOR_MEDIA.value,
        ReupQueueStatus.WAITING_FOR_METADATA.value,
        ReupQueueStatus.PROCESSING.value,
    }
    if held_at and in_flight_queue:
        return 2
    if status == ReupQueueStatus.PROCESSING.value:
        return 0
    if job in {JobStatus.RUNNING.value, JobStatus.WAITING_FOR_REVIEW.value}:
        return 0
    if job in {JobStatus.QUEUED.value, JobStatus.RETRYABLE.value}:
        return 1
    if status == ReupQueueStatus.FAILED_NEEDS_ATTENTION.value or blocked:
        return 3
    if status == ReupQueueStatus.READY_FOR_PROCESSING.value:
        return 4
    return 5


def active_first_order_rank_expr() -> Case:
    in_flight = ReupQueueItem.status.in_(
        (
            ReupQueueStatus.WAITING_FOR_MEDIA,
            ReupQueueStatus.WAITING_FOR_METADATA,
            ReupQueueStatus.PROCESSING,
        )
    )
    return case(
        (
            (ReupQueueItem.held_at.is_not(None)) & in_flight,
            2,
        ),
        (
            (ReupQueueItem.status == ReupQueueStatus.PROCESSING)
            | Job.status.in_((JobStatus.RUNNING, JobStatus.WAITING_FOR_REVIEW)),
            0,
        ),
        (
            Job.status.in_((JobStatus.QUEUED, JobStatus.RETRYABLE)),
            1,
        ),
        (
            (ReupQueueItem.status == ReupQueueStatus.FAILED_NEEDS_ATTENTION)
            | ReupQueueItem.blocked_reason.is_not(None),
            3,
        ),
        (
            ReupQueueItem.status == ReupQueueStatus.READY_FOR_PROCESSING,
            4,
        ),
        else_=5,
    )


def order_clauses_for_sort(sort: str | None) -> list[ColumnElement]:
    normalized = normalize_reup_queue_sort(sort)
    if normalized == "newest":
        return [
            ReupQueueItem.queued_at.desc().nullslast(),
            ReupQueueItem.created_at.desc(),
        ]
    if normalized == "ready_first":
        return [
            case(
                (ReupQueueItem.status == ReupQueueStatus.READY_FOR_PROCESSING, 0),
                (ReupQueueItem.status == ReupQueueStatus.PROCESSING, 1),
                (
                    ReupQueueItem.status.in_(
                        (ReupQueueStatus.WAITING_FOR_MEDIA, ReupQueueStatus.WAITING_FOR_METADATA)
                    ),
                    2,
                ),
                else_=3,
            ).asc(),
            ReupQueueItem.queued_at.desc().nullslast(),
            ReupQueueItem.created_at.desc(),
        ]
    if normalized == "needs_attention_first":
        return [
            case(
                (ReupQueueItem.status == ReupQueueStatus.FAILED_NEEDS_ATTENTION, 0),
                (ReupQueueItem.blocked_reason.is_not(None), 1),
                (
                    ReupQueueItem.status.in_(
                        (ReupQueueStatus.WAITING_FOR_MEDIA, ReupQueueStatus.WAITING_FOR_METADATA)
                    ),
                    2,
                ),
                else_=3,
            ).asc(),
            ReupQueueItem.queued_at.desc().nullslast(),
            ReupQueueItem.created_at.desc(),
        ]
    if normalized == "export_ready_first":
        return [
            case(
                (ReupQueueItem.status == ReupQueueStatus.READY_TO_EXPORT, 0),
                (ReupQueueItem.status == ReupQueueStatus.EXPORT_PACKAGE_CREATED, 1),
                (
                    ReupQueueItem.status.in_(
                        (ReupQueueStatus.READY_TO_PUBLISH, ReupQueueStatus.PUBLISH_HANDOFF_CREATED)
                    ),
                    2,
                ),
                else_=3,
            ).asc(),
            ReupQueueItem.queued_at.desc().nullslast(),
            ReupQueueItem.created_at.desc(),
        ]
    # active_first (default): join Job so RUNNING downloads land on page 1.
    return [
        active_first_order_rank_expr().asc(),
        Job.progress_percent.desc().nullslast(),
        ReupQueueItem.queued_at.desc().nullslast(),
        ReupQueueItem.created_at.desc(),
    ]


def sort_requires_job_join(sort: str | None) -> bool:
    return normalize_reup_queue_sort(sort) == "active_first"
