from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishDraftStatus, PublishReconciliationStatus
from src.models.publish import PublishAttempt, PublishDraft
from src.publish.connectors.base import PublishConnector
from src.publish.services.publish_attempt_service import ACTIVE_ATTEMPT_STATUSES, PublishAttemptError, PublishAttemptService
from src.publish.services.publish_lifecycle_service import PublishLifecycleService


class PublishReconciliationError(ValueError):
    pass


class PublishReconciliationService:
    stale_after = timedelta(hours=2)

    def __init__(self, db: Session, connector: PublishConnector | None = None):
        self.db = db
        self.attempts = PublishAttemptService(db, connector=connector)
        self.lifecycle = PublishLifecycleService(db)

    def build_publication_summary(self, draft_id: UUID) -> dict:
        draft = self._get_draft(draft_id)
        attempts = self.attempts.attempts_for_draft(draft_id)
        canonical = self.attempts.canonical_for_draft(draft_id)
        latest = attempts[0] if attempts else None
        needs_reconciliation = [attempt for attempt in attempts if attempt.status == PublishAttemptStatus.NEEDS_RECONCILIATION or attempt.reconciliation_required]
        active = [attempt for attempt in attempts if attempt.status in ACTIVE_ATTEMPT_STATUSES]
        duplicate_success_count = max(len([attempt for attempt in attempts if attempt.external_status == ExternalPublicationStatus.PUBLISHED]) - 1, 0)
        return {
            "publish_draft_id": str(draft.id),
            "draft_status": draft.status.value,
            "current_publication_status": draft.current_publication_status.value,
            "canonical_publish_attempt_id": str(canonical.id) if canonical else None,
            "latest_publish_attempt_id": str(latest.id) if latest else None,
            "current_external_publish_id": draft.current_external_publish_id,
            "current_external_permalink": draft.current_external_permalink,
            "published_at": draft.published_at.isoformat() if draft.published_at else None,
            "last_publish_synced_at": draft.last_publish_synced_at.isoformat() if draft.last_publish_synced_at else None,
            "attempt_count": len(attempts),
            "active_attempt_count": len(active),
            "needs_reconciliation_count": len(needs_reconciliation),
            "duplicate_success_count": duplicate_success_count,
            "requires_operator_attention": draft.status == PublishDraftStatus.NEEDS_ATTENTION or bool(needs_reconciliation),
            "warnings": self._build_warnings(draft, attempts, duplicate_success_count),
        }

    def reconcile_draft(self, draft_id: UUID) -> dict:
        draft = self._get_draft(draft_id)
        attempts = self.attempts.attempts_for_draft(draft_id)
        refreshed_attempt_ids: list[str] = []
        stale_attempt_ids: list[str] = []
        errors: list[dict] = []

        for attempt in attempts:
            if self._is_stale_active_attempt(attempt):
                stale_attempt_ids.append(str(attempt.id))
                self._mark_stale_attempt(attempt)
                self.db.commit()

            if self._should_refresh(attempt):
                try:
                    refreshed = self.attempts.refresh_attempt_status(attempt.id)
                    refreshed_attempt_ids.append(str(refreshed.id))
                except (PublishAttemptError, ValueError) as exc:
                    errors.append({"publish_attempt_id": str(attempt.id), "error": str(exc)})

        self.lifecycle.sync_attempt_to_draft(draft, self.attempts.attempts_for_draft(draft_id))
        self.db.commit()
        return {
            "publish_draft_id": str(draft.id),
            "refreshed_attempt_ids": refreshed_attempt_ids,
            "stale_attempt_ids": stale_attempt_ids,
            "errors": errors,
            "summary": self.build_publication_summary(draft_id),
        }

    def refresh_attempt(self, attempt_id: UUID) -> PublishAttempt:
        return self.attempts.refresh_attempt_status(attempt_id)

    def _get_draft(self, draft_id: UUID) -> PublishDraft:
        try:
            return self.attempts.get_draft_for_status(draft_id)
        except PublishAttemptError as exc:
            raise PublishReconciliationError(str(exc)) from exc

    def _should_refresh(self, attempt: PublishAttempt) -> bool:
        if not (attempt.external_publish_id or attempt.external_media_id or attempt.external_reel_id):
            return False
        return attempt.status in {
            PublishAttemptStatus.NEEDS_RECONCILIATION,
            PublishAttemptStatus.RECONCILING,
            PublishAttemptStatus.AWAITING_PLATFORM_CONFIRMATION,
        } or attempt.reconciliation_required

    def _is_stale_active_attempt(self, attempt: PublishAttempt) -> bool:
        started_at = attempt.started_at or attempt.created_at
        if started_at is None or attempt.status not in ACTIVE_ATTEMPT_STATUSES:
            return False
        return datetime.now(UTC) - started_at > self.stale_after

    def _mark_stale_attempt(self, attempt: PublishAttempt) -> None:
        if attempt.external_publish_id or attempt.external_media_id or attempt.external_reel_id:
            attempt.status = PublishAttemptStatus.NEEDS_RECONCILIATION
            attempt.reconciliation_required = True
            attempt.reconciliation_status = PublishReconciliationStatus.REQUIRED
            attempt.error_code = attempt.error_code or "stale_attempt_state"
            attempt.error_message = attempt.error_message or "Attempt ran too long with an external reference and needs status reconciliation."
        else:
            attempt.status = PublishAttemptStatus.FAILED
            attempt.reconciliation_required = False
            attempt.reconciliation_status = PublishReconciliationStatus.RESOLVED_FAILURE
            attempt.error_code = attempt.error_code or "stale_attempt_state"
            attempt.error_message = attempt.error_message or "Attempt ran too long without an external reference."
            attempt.finished_at = datetime.now(UTC)

    def _build_warnings(self, draft: PublishDraft, attempts: list[PublishAttempt], duplicate_success_count: int) -> list[str]:
        warnings: list[str] = []
        if draft.status == PublishDraftStatus.NEEDS_ATTENTION:
            warnings.append("latest_publish_state_needs_operator_attention")
        if any(attempt.status == PublishAttemptStatus.NEEDS_RECONCILIATION for attempt in attempts):
            warnings.append("attempt_needs_reconciliation")
        if duplicate_success_count:
            warnings.append("duplicate_successful_publish_attempts")
        if any(attempt.external_status in {ExternalPublicationStatus.UNKNOWN, ExternalPublicationStatus.PARTIALLY_CONFIRMED} for attempt in attempts):
            warnings.append("ambiguous_platform_status_present")
        return warnings
