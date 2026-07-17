from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session, selectinload

from src.downloaders.errors import DownloadError
from src.enums import CandidateStatus, ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.models.export_handoff import ExportPackageItem
from src.models.jobs import Job
from src.models.reup_queue import ReupQueueItem
from src.models.review import VideoCandidate
from src.services.reup_queue_list_sort import order_clauses_for_sort, sort_requires_job_join

logger = logging.getLogger(__name__)

ACTIVE_REUP_QUEUE_STATUSES = {
    ReupQueueStatus.READY_FOR_PROCESSING,
    ReupQueueStatus.WAITING_FOR_MEDIA,
    ReupQueueStatus.WAITING_FOR_METADATA,
    ReupQueueStatus.PROCESSING,
    ReupQueueStatus.READY_TO_EXPORT,
    ReupQueueStatus.EXPORT_PACKAGE_CREATED,
    ReupQueueStatus.READY_TO_PUBLISH,
    ReupQueueStatus.PUBLISH_HANDOFF_CREATED,
    ReupQueueStatus.FAILED_NEEDS_ATTENTION,
}

TERMINAL_REUP_QUEUE_STATUSES = {ReupQueueStatus.COMPLETED, ReupQueueStatus.CANCELLED}

OPERATOR_CLEARABLE_STATUSES = {
    ReupQueueStatus.COMPLETED,
    ReupQueueStatus.CANCELLED,
    ReupQueueStatus.FAILED_NEEDS_ATTENTION,
}


def is_active_reup_queue_status(status: ReupQueueStatus) -> bool:
    return status in ACTIVE_REUP_QUEUE_STATUSES


class ReupQueueError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ReupQueueEnqueueResult:
    requested_count: int
    queued_count: int
    already_queued_count: int
    skipped_count: int
    items: list[ReupQueueItem]
    skipped_candidate_ids: list[UUID]


@dataclass(frozen=True)
class ReupQueueCandidateMembership:
    in_reup_queue: bool = False
    reup_queue_item_id: UUID | None = None
    reup_queue_status: ReupQueueStatus | None = None


@dataclass(frozen=True)
class ReupQueuePurgeResult:
    requested_count: int
    purged_count: int
    skipped_count: int
    skipped_item_ids: list[UUID]
    purged_item_ids: list[UUID]


@dataclass(frozen=True)
class ReupQueueAvailableAction:
    action: ReupQueueAction
    label: str
    description: str
    requires_note: bool = False


ACTION_COPY: dict[ReupQueueAction, tuple[str, str, bool]] = {
    ReupQueueAction.START_PROCESSING: ("Start processing", "Move this approved item into explicit downstream preparation.", False),
    ReupQueueAction.MARK_MEDIA_READY: (
        "Mark media ready",
        "Confirm source media is ready and enqueue audio analysis (speech gate / transcript prep).",
        False,
    ),
    ReupQueueAction.MARK_BLOCKED: ("Mark blocked", "Record a safe blocked reason that requires operator attention.", True),
    ReupQueueAction.HOLD: ("Pause", "Pause in-progress work and stop the active download job without cancelling the queue item.", False),
    ReupQueueAction.RESUME: ("Resume", "Resume paused work and restart download when needed.", False),
    ReupQueueAction.RETRY: ("Retry", "Clear failure context and return this item to processing readiness.", False),
    ReupQueueAction.CANCEL: ("Cancel", "Remove this item from active downstream work.", True),
    ReupQueueAction.MARK_COMPLETED: ("Mark completed", "Close the queue item after downstream work is known complete.", False),
    ReupQueueAction.DISMISS: ("Dismiss", "Hide this item from the operator queue without deleting source media.", False),
}

ALLOWED_ACTIONS_BY_STATUS: dict[ReupQueueStatus, set[ReupQueueAction]] = {
    ReupQueueStatus.READY_FOR_PROCESSING: {ReupQueueAction.START_PROCESSING, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.HOLD, ReupQueueAction.CANCEL},
    ReupQueueStatus.WAITING_FOR_MEDIA: {ReupQueueAction.MARK_MEDIA_READY, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.CANCEL},
    ReupQueueStatus.WAITING_FOR_METADATA: {ReupQueueAction.MARK_MEDIA_READY, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.CANCEL},
    ReupQueueStatus.PROCESSING: {ReupQueueAction.MARK_MEDIA_READY, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.HOLD, ReupQueueAction.CANCEL, ReupQueueAction.MARK_COMPLETED},
    ReupQueueStatus.READY_TO_EXPORT: {ReupQueueAction.MARK_COMPLETED, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.CANCEL},
    ReupQueueStatus.EXPORT_PACKAGE_CREATED: {ReupQueueAction.MARK_COMPLETED, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.CANCEL},
    ReupQueueStatus.READY_TO_PUBLISH: {ReupQueueAction.MARK_COMPLETED, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.CANCEL},
    ReupQueueStatus.PUBLISH_HANDOFF_CREATED: {ReupQueueAction.MARK_COMPLETED, ReupQueueAction.MARK_BLOCKED, ReupQueueAction.CANCEL},
    ReupQueueStatus.FAILED_NEEDS_ATTENTION: {ReupQueueAction.RETRY, ReupQueueAction.RESUME, ReupQueueAction.CANCEL, ReupQueueAction.DISMISS},
    ReupQueueStatus.COMPLETED: {ReupQueueAction.DISMISS},
    ReupQueueStatus.CANCELLED: {ReupQueueAction.DISMISS},
}


def utc_now() -> datetime:
    return datetime.now(UTC)


class ReupQueueService:
    def __init__(self, db: Session, *, download_service=None, audio_analysis_service=None):
        self.db = db
        self._download_service_override = download_service
        self._audio_analysis_service_override = audio_analysis_service

    def _get_download_service(self):
        if self._download_service_override is not None:
            return self._download_service_override
        from src.services.download_service import DownloadService

        return DownloadService(self.db)

    def _get_audio_analysis_service(self):
        if self._audio_analysis_service_override is not None:
            return self._audio_analysis_service_override
        from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService

        return AudioAnalysisService(self.db)

    def list_items(
        self,
        *,
        status: ReupQueueStatus | None = None,
        statuses: list[ReupQueueStatus] | None = None,
        include_dismissed: bool = False,
        sort: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ReupQueueItem], int, dict[str, int]]:
        stmt: Select[tuple[ReupQueueItem]] = select(ReupQueueItem).options(
            selectinload(ReupQueueItem.source_video),
            selectinload(ReupQueueItem.video_candidate),
            selectinload(ReupQueueItem.job),
        )
        if sort_requires_job_join(sort):
            stmt = stmt.outerjoin(Job, ReupQueueItem.job_id == Job.id)
        count_stmt = select(func.count()).select_from(ReupQueueItem)
        status_counts_stmt = select(ReupQueueItem.status, func.count()).select_from(ReupQueueItem).group_by(ReupQueueItem.status)

        status_filter_values: list[ReupQueueStatus] = []
        if statuses:
            status_filter_values = list(statuses)
        elif status is not None:
            status_filter_values = [status]

        if status_filter_values:
            stmt = stmt.where(ReupQueueItem.status.in_(status_filter_values))
            count_stmt = count_stmt.where(ReupQueueItem.status.in_(status_filter_values))
        if not include_dismissed:
            stmt = stmt.where(ReupQueueItem.operator_dismissed_at.is_(None))
            count_stmt = count_stmt.where(ReupQueueItem.operator_dismissed_at.is_(None))
            status_counts_stmt = status_counts_stmt.where(ReupQueueItem.operator_dismissed_at.is_(None))

        stmt = stmt.order_by(*order_clauses_for_sort(sort)).limit(limit).offset(offset)
        items = list(self.db.scalars(stmt).unique())
        total = int(self.db.scalar(count_stmt) or 0)
        status_counts: dict[str, int] = {}
        for row_status, row_count in self.db.execute(status_counts_stmt).all():
            key = row_status.value if hasattr(row_status, "value") else str(row_status)
            status_counts[key] = int(row_count or 0)
        return items, total, status_counts

    def get_item(self, item_id: UUID) -> ReupQueueItem:
        item = self.db.scalar(
            select(ReupQueueItem)
            .where(ReupQueueItem.id == item_id)
            .options(
                selectinload(ReupQueueItem.source_video),
                selectinload(ReupQueueItem.video_candidate),
                selectinload(ReupQueueItem.job),
            )
        )
        if item is None:
            raise ReupQueueError("REUP_QUEUE_ITEM_NOT_FOUND", "Reup Queue item was not found.")
        return item

    def membership_for_candidates(self, candidate_ids: list[UUID]) -> dict[UUID, ReupQueueCandidateMembership]:
        if not candidate_ids:
            return {}
        items = list(
            self.db.scalars(select(ReupQueueItem).where(ReupQueueItem.video_candidate_id.in_(candidate_ids))).unique()
        )
        items_by_candidate_id = {item.video_candidate_id: item for item in items}
        return {
            candidate_id: ReupQueueCandidateMembership(
                in_reup_queue=candidate_id in items_by_candidate_id and is_active_reup_queue_status(items_by_candidate_id[candidate_id].status),
                reup_queue_item_id=items_by_candidate_id[candidate_id].id if candidate_id in items_by_candidate_id else None,
                reup_queue_status=items_by_candidate_id[candidate_id].status if candidate_id in items_by_candidate_id else None,
            )
            for candidate_id in candidate_ids
        }

    def enqueue_candidates(
        self,
        *,
        candidate_ids: list[UUID],
        priority: int = 100,
        queued_reason: str | None = "review_board_approved",
        operator_note: str | None = None,
    ) -> ReupQueueEnqueueResult:
        candidates = list(
            self.db.scalars(
                select(VideoCandidate)
                .where(VideoCandidate.id.in_(candidate_ids))
                .options(selectinload(VideoCandidate.source_video))
            ).unique()
        )
        candidates_by_id = {candidate.id: candidate for candidate in candidates}
        existing_items = list(
            self.db.scalars(
                select(ReupQueueItem)
                .where(ReupQueueItem.video_candidate_id.in_(candidate_ids))
                .options(
                selectinload(ReupQueueItem.source_video),
                selectinload(ReupQueueItem.video_candidate),
                selectinload(ReupQueueItem.job),
            )
            ).unique()
        )
        existing_by_candidate_id = {item.video_candidate_id: item for item in existing_items}
        queued_items: list[ReupQueueItem] = []
        already_queued_items: list[ReupQueueItem] = []
        skipped_candidate_ids: list[UUID] = []
        now = utc_now()

        for candidate_id in candidate_ids:
            candidate = candidates_by_id.get(candidate_id)
            if candidate is None or candidate.status != CandidateStatus.APPROVED:
                skipped_candidate_ids.append(candidate_id)
                continue
            existing = existing_by_candidate_id.get(candidate_id)
            if existing is not None:
                if existing.status in TERMINAL_REUP_QUEUE_STATUSES:
                    self._reactivate_terminal_item(
                        existing,
                        priority=priority,
                        queued_reason=queued_reason,
                        operator_note=operator_note,
                        now=now,
                    )
                    queued_items.append(existing)
                    continue
                already_queued_items.append(existing)
                continue
            item = ReupQueueItem(
                workspace_id=candidate.workspace_id,
                video_candidate_id=candidate.id,
                source_video_id=candidate.source_video_id,
                status=ReupQueueStatus.READY_FOR_PROCESSING,
                media_prep_status=ReupQueueMediaPrepStatus.NOT_STARTED,
                priority=priority,
                queued_reason=queued_reason,
                operator_note=operator_note,
                queued_at=now,
                metadata_json={"source": "review_board"},
            )
            self.db.add(item)
            queued_items.append(item)

        self.db.commit()
        for item in queued_items + already_queued_items:
            self.db.refresh(item)

        logger.info(
            "reup_queue_enqueue_candidates",
            extra={
                "requested_count": len(candidate_ids),
                "queued_count": len(queued_items),
                "already_queued_count": len(already_queued_items),
                "skipped_count": len(skipped_candidate_ids),
            },
        )
        return ReupQueueEnqueueResult(
            requested_count=len(candidate_ids),
            queued_count=len(queued_items),
            already_queued_count=len(already_queued_items),
            skipped_count=len(skipped_candidate_ids),
            items=queued_items + already_queued_items,
            skipped_candidate_ids=skipped_candidate_ids,
        )

    def _reactivate_terminal_item(
        self,
        item: ReupQueueItem,
        *,
        priority: int,
        queued_reason: str | None,
        operator_note: str | None,
        now: datetime,
    ) -> None:
        item.status = ReupQueueStatus.READY_FOR_PROCESSING
        item.media_prep_status = ReupQueueMediaPrepStatus.NOT_STARTED
        item.priority = priority
        item.queued_reason = queued_reason
        item.operator_note = operator_note
        item.queued_at = now
        item.job_id = None
        item.last_error_code = None
        item.last_error_message = None
        item.failed_at = None
        item.blocked_at = None
        item.blocked_reason = None
        item.held_at = None
        item.completed_at = None
        item.cancelled_at = None
        item.operator_dismissed_at = None
        item.metadata_json = {"source": "review_board"}

    def apply_action(
        self,
        item_id: UUID,
        *,
        action: ReupQueueAction,
        note: str | None = None,
        blocked_reason: str | None = None,
        media_prep_notes: str | None = None,
        media_prep_status: ReupQueueMediaPrepStatus | None = None,
    ) -> ReupQueueItem:
        item = self.get_item(item_id)
        if action not in available_action_values(item):
            raise ReupQueueError("INVALID_REUP_QUEUE_ACTION", f"Action {action} is not allowed while item is {item.status}.")

        now = utc_now()
        from_status = item.status
        item.last_action = action
        item.last_action_at = now
        item.last_action_note = note

        if action == ReupQueueAction.START_PROCESSING:
            item.started_at = item.started_at or now
            item.held_at = None
            item.blocked_at = None
            item.blocked_reason = None
            item.last_error_code = None
            item.last_error_message = None
            item.failed_at = None
            try:
                item.job_id = self._ensure_download_job_id(item)
            except DownloadError as exc:
                item.status = ReupQueueStatus.FAILED_NEEDS_ATTENTION
                item.media_prep_status = ReupQueueMediaPrepStatus.BLOCKED
                item.failed_at = now
                item.last_error_code = str(exc.code)
                item.last_error_message = exc.message
            else:
                item.status = ReupQueueStatus.WAITING_FOR_MEDIA
                item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA
        elif action == ReupQueueAction.MARK_MEDIA_READY:
            from src.audio_pipeline.errors import AudioAnalysisError

            item.media_ready_at = now
            item.media_prep_notes = media_prep_notes or note or item.media_prep_notes
            # Localization path: confirm media always enters analysis prep (not export skip).
            if media_prep_status is not None and media_prep_status not in {
                ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
                ReupQueueMediaPrepStatus.READY_FOR_EXPORT,
            }:
                raise ReupQueueError("INVALID_MEDIA_PREP_STATUS", "Media-ready action can only move to metadata prep or export readiness.")
            item.blocked_at = None
            item.blocked_reason = None
            try:
                item.job_id = self._ensure_analyze_audio_job_id(item)
            except AudioAnalysisError as exc:
                item.status = ReupQueueStatus.FAILED_NEEDS_ATTENTION
                item.media_prep_status = ReupQueueMediaPrepStatus.BLOCKED
                item.failed_at = now
                item.last_error_code = str(exc.code)
                item.last_error_message = exc.message
            else:
                item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_METADATA
                item.status = ReupQueueStatus.WAITING_FOR_METADATA
                meta = dict(item.metadata_json or {})
                meta["analyze_audio_job_id"] = str(item.job_id)
                item.metadata_json = meta
        elif action == ReupQueueAction.MARK_BLOCKED:
            reason = blocked_reason or note
            if not reason:
                raise ReupQueueError("BLOCKED_REASON_REQUIRED", "A safe blocked reason is required.")
            item.blocked_reason = reason
            item.blocked_at = now
            item.media_prep_status = ReupQueueMediaPrepStatus.BLOCKED
            item.status = ReupQueueStatus.FAILED_NEEDS_ATTENTION
            item.failed_at = now
            item.last_error_code = "OPERATOR_BLOCKED"
            item.last_error_message = reason
        elif action == ReupQueueAction.HOLD:
            hold_note = (note or blocked_reason or "").strip() or "Operator paused progress"
            self._cancel_linked_download_job(item)
            item.held_at = now
            item.last_action_note = hold_note
            # Do not set blocked_reason — Hold is pause, not attention/blocked.
            if item.status in {
                ReupQueueStatus.WAITING_FOR_MEDIA,
                ReupQueueStatus.WAITING_FOR_METADATA,
                ReupQueueStatus.PROCESSING,
            }:
                item.status = ReupQueueStatus.WAITING_FOR_MEDIA
                item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA
        elif action == ReupQueueAction.RESUME:
            item.held_at = None
            item.blocked_at = None
            item.blocked_reason = None
            item.last_error_code = None
            item.last_error_message = None
            item.failed_at = None
            if item.media_prep_status == ReupQueueMediaPrepStatus.BLOCKED:
                item.media_prep_status = ReupQueueMediaPrepStatus.NOT_STARTED
            # Paused download / in-progress media wait: restart download job.
            if item.status in {
                ReupQueueStatus.WAITING_FOR_MEDIA,
                ReupQueueStatus.WAITING_FOR_METADATA,
                ReupQueueStatus.PROCESSING,
            } or item.started_at is not None:
                prior_job_id = item.job_id
                item.job_id = None
                item.started_at = item.started_at or now
                if prior_job_id is not None:
                    # Also covers Pause runs before key-release existed (stuck cancelled jobs).
                    self._release_download_job_idempotency_slot(prior_job_id)
                try:
                    item.job_id = self._ensure_download_job_id(item)
                except DownloadError as exc:
                    item.status = ReupQueueStatus.FAILED_NEEDS_ATTENTION
                    item.media_prep_status = ReupQueueMediaPrepStatus.BLOCKED
                    item.failed_at = now
                    item.last_error_code = str(exc.code)
                    item.last_error_message = exc.message
                else:
                    item.status = ReupQueueStatus.WAITING_FOR_MEDIA
                    item.media_prep_status = ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA
            else:
                item.status = ReupQueueStatus.READY_FOR_PROCESSING
                if item.media_prep_status == ReupQueueMediaPrepStatus.BLOCKED:
                    item.media_prep_status = ReupQueueMediaPrepStatus.NOT_STARTED
        elif action == ReupQueueAction.RETRY:
            item.status = ReupQueueStatus.READY_FOR_PROCESSING
            item.media_prep_status = ReupQueueMediaPrepStatus.NOT_STARTED
            item.job_id = None
            item.last_error_code = None
            item.last_error_message = None
            item.failed_at = None
            item.blocked_at = None
            item.blocked_reason = None
            item.held_at = None
            item.completed_at = None
            item.cancelled_at = None
        elif action == ReupQueueAction.CANCEL:
            item.status = ReupQueueStatus.CANCELLED
            item.cancelled_at = now
            item.blocked_reason = blocked_reason or note or item.blocked_reason
        elif action == ReupQueueAction.MARK_COMPLETED:
            item.status = ReupQueueStatus.COMPLETED
            item.completed_at = now
            item.cancelled_at = None
        elif action == ReupQueueAction.DISMISS:
            if item.status not in OPERATOR_CLEARABLE_STATUSES:
                raise ReupQueueError("INVALID_REUP_QUEUE_ACTION", f"Dismiss is not allowed while item is {item.status}.")
            item.operator_dismissed_at = now
            item.last_action_note = note or item.last_action_note

        self.db.commit()
        self.db.refresh(item)
        logger.info(
            "reup_queue_action_applied",
            extra={
                "reup_queue_item_id": str(item.id),
                "workspace_id": str(item.workspace_id),
                "video_candidate_id": str(item.video_candidate_id),
                "source_video_id": str(item.source_video_id),
                "action": action,
                "from_status": from_status,
                "to_status": item.status,
            },
        )
        return self.get_item(item.id)

    def purge_clearable_items(self, *, item_ids: list[UUID] | None = None) -> ReupQueuePurgeResult:
        stmt = select(ReupQueueItem).where(ReupQueueItem.status.in_(OPERATOR_CLEARABLE_STATUSES))
        if item_ids is not None:
            stmt = stmt.where(ReupQueueItem.id.in_(item_ids))
        items = list(self.db.scalars(stmt).unique())
        requested_count = len(items)
        if not items:
            return ReupQueuePurgeResult(requested_count=0, purged_count=0, skipped_count=0, skipped_item_ids=[], purged_item_ids=[])

        purge_ids = [item.id for item in items]
        linked_ids = set(
            self.db.scalars(select(ExportPackageItem.reup_queue_item_id).where(ExportPackageItem.reup_queue_item_id.in_(purge_ids))).all()
        )
        deletable_ids = [item_id for item_id in purge_ids if item_id not in linked_ids]
        skipped_item_ids = [item_id for item_id in purge_ids if item_id in linked_ids]

        if deletable_ids:
            self.db.execute(delete(ReupQueueItem).where(ReupQueueItem.id.in_(deletable_ids)))
            self.db.commit()
            logger.info(
                "reup_queue_items_purged",
                extra={
                    "requested_count": requested_count,
                    "purged_count": len(deletable_ids),
                    "skipped_count": len(skipped_item_ids),
                },
            )

        return ReupQueuePurgeResult(
            requested_count=requested_count,
            purged_count=len(deletable_ids),
            skipped_count=len(skipped_item_ids),
            skipped_item_ids=skipped_item_ids,
            purged_item_ids=deletable_ids,
        )

    def _ensure_download_job_id(self, item: ReupQueueItem) -> UUID:
        from src.services.download_service import DownloadRequest

        if item.job_id is not None:
            return item.job_id
        result = self._get_download_service().create_download_job(
            DownloadRequest(
                source_video_id=item.source_video_id,
                candidate_id=item.video_candidate_id,
                force_refresh=True,
            ),
            idempotency_key=f"reup-queue:{item.id}:download",
        )
        return UUID(result.job_id)

    def _ensure_analyze_audio_job_id(self, item: ReupQueueItem) -> UUID:
        from src.audio_pipeline.types import AudioAnalysisRequest, TranslationPreset
        from src.enums import JobType
        from src.models.jobs import Job

        if item.job_id is not None:
            job = self.db.get(Job, item.job_id)
            if job is not None and str(job.job_type) == JobType.ANALYZE_AUDIO:
                return item.job_id
        job = self._get_audio_analysis_service().create_analysis_job(
            AudioAnalysisRequest(
                source_video_id=item.source_video_id,
                translation_preset=TranslationPreset.LITERAL_SAFE,
                force_refresh=False,
                skip_translation=True,
            ),
            idempotency_key=f"reup-queue:{item.id}:analyze-audio",
        )
        return job.id

    def _cancel_linked_download_job(self, item: ReupQueueItem) -> None:
        if item.job_id is None:
            return
        from src.services.job_service import JobService

        try:
            JobService(self.db).cancel_job(item.job_id)
        except ValueError:
            # Job already terminal or not cancellable — still treat queue item as paused.
            logger.info(
                "reup_queue_hold_job_not_cancellable",
                extra={"reup_queue_item_id": str(item.id), "job_id": str(item.job_id)},
            )
        # Free unique (workspace, idempotency_key) so Resume can recreate with the same logical key.
        self._release_download_job_idempotency_slot(item.job_id)

    def _release_download_job_idempotency_slot(self, job_id: UUID) -> None:
        from src.models.jobs import Job

        job = self.db.get(Job, job_id)
        if job is None:
            return
        key = job.idempotency_key
        if not key:
            return
        marker = f":cancelled:{job.id}"
        if key.endswith(marker):
            return
        job.idempotency_key = f"{key}{marker}"
        logger.info(
            "reup_queue_download_idempotency_released",
            extra={"job_id": str(job.id), "previous_key": key},
        )


def available_actions_for_item(item: ReupQueueItem) -> list[ReupQueueAvailableAction]:
    return [
        ReupQueueAvailableAction(action=action, label=ACTION_COPY[action][0], description=ACTION_COPY[action][1], requires_note=ACTION_COPY[action][2])
        for action in sorted(available_action_values(item), key=lambda value: value.value)
    ]


def available_action_values(item: ReupQueueItem) -> set[ReupQueueAction]:
    actions = set(ALLOWED_ACTIONS_BY_STATUS[item.status])
    if item.status == ReupQueueStatus.WAITING_FOR_METADATA and item.media_prep_status == ReupQueueMediaPrepStatus.READY_FOR_EXPORT:
        actions.add(ReupQueueAction.MARK_COMPLETED)
    held = getattr(item, "held_at", None) is not None
    if item.status in {
        ReupQueueStatus.WAITING_FOR_MEDIA,
        ReupQueueStatus.WAITING_FOR_METADATA,
        ReupQueueStatus.PROCESSING,
    }:
        if held:
            actions.add(ReupQueueAction.RESUME)
            actions.discard(ReupQueueAction.HOLD)
        else:
            actions.add(ReupQueueAction.HOLD)
            actions.discard(ReupQueueAction.RESUME)
    elif item.status == ReupQueueStatus.READY_FOR_PROCESSING:
        if held:
            actions.add(ReupQueueAction.RESUME)
            actions.discard(ReupQueueAction.HOLD)
    return actions


def bucket_for_status(status: ReupQueueStatus) -> str:
    return {
        ReupQueueStatus.READY_FOR_PROCESSING: "Ready for processing",
        ReupQueueStatus.WAITING_FOR_MEDIA: "Waiting for media",
        ReupQueueStatus.WAITING_FOR_METADATA: "Waiting for metadata prep",
        ReupQueueStatus.PROCESSING: "Processing",
        ReupQueueStatus.READY_TO_EXPORT: "Ready to export",
        ReupQueueStatus.EXPORT_PACKAGE_CREATED: "Export package created",
        ReupQueueStatus.READY_TO_PUBLISH: "Ready to publish",
        ReupQueueStatus.PUBLISH_HANDOFF_CREATED: "Publish handoff created",
        ReupQueueStatus.FAILED_NEEDS_ATTENTION: "Failed / needs attention",
        ReupQueueStatus.COMPLETED: "Completed",
        ReupQueueStatus.CANCELLED: "Cancelled",
    }[status]


def next_action_for_status(status: ReupQueueStatus) -> str:
    return {
        ReupQueueStatus.READY_FOR_PROCESSING: "Start downstream processing or block the item with a safe reason.",
        ReupQueueStatus.WAITING_FOR_MEDIA: "Attach or confirm source media, then mark media ready.",
        ReupQueueStatus.WAITING_FOR_METADATA: "Prepare caption, language, and media-prep metadata before export.",
        ReupQueueStatus.PROCESSING: "Continue media preparation, mark media ready, hold, block, or cancel.",
        ReupQueueStatus.READY_TO_EXPORT: "Create an Export Package or mark completed if export is already done.",
        ReupQueueStatus.EXPORT_PACKAGE_CREATED: "Inspect the package, create a Publish Handoff, or mark completed if downstream work is done.",
        ReupQueueStatus.READY_TO_PUBLISH: "Create or inspect a Publish Handoff before external publish work.",
        ReupQueueStatus.PUBLISH_HANDOFF_CREATED: "Inspect the Publish Handoff and continue manual downstream publishing outside this queue.",
        ReupQueueStatus.FAILED_NEEDS_ATTENTION: "Inspect the safe reason, then retry, resume, or cancel.",
        ReupQueueStatus.COMPLETED: "No action required.",
        ReupQueueStatus.CANCELLED: "No action required unless a future re-queue path is introduced.",
    }[status]
