from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishDraftStatus, PublishReconciliationStatus
from src.models.publish import PublishAttempt, PublishDraft


class PublishLifecycleService:
    def __init__(self, db: Session):
        self.db = db

    def sync_attempt_to_draft(self, draft: PublishDraft, attempts: list[PublishAttempt]) -> None:
        latest = attempts[0] if attempts else None
        canonical = self._select_canonical_attempt(attempts)

        draft.latest_publish_attempt_id = latest.id if latest else None
        draft.canonical_publish_attempt_id = canonical.id if canonical else None

        if canonical is not None:
            draft.status = PublishDraftStatus.PUBLISHED
            draft.current_publication_status = canonical.external_status
            draft.current_external_publish_id = canonical.external_publish_id or canonical.external_reel_id
            draft.current_external_permalink = canonical.external_permalink
            draft.published_at = canonical.finished_at or canonical.last_status_checked_at
            draft.last_publish_synced_at = canonical.last_status_checked_at or canonical.finished_at
        elif latest is not None:
            draft.current_publication_status = latest.external_status
            draft.current_external_publish_id = latest.external_publish_id or latest.external_reel_id
            draft.current_external_permalink = latest.external_permalink
            draft.last_publish_synced_at = latest.last_status_checked_at or latest.finished_at
            if latest.status in {
                PublishAttemptStatus.RUNNING,
                PublishAttemptStatus.UPLOADING,
                PublishAttemptStatus.PUBLISHING,
                PublishAttemptStatus.AWAITING_PLATFORM_CONFIRMATION,
                PublishAttemptStatus.RECONCILING,
            }:
                draft.status = PublishDraftStatus.PUBLISHING
            elif latest.status == PublishAttemptStatus.NEEDS_RECONCILIATION:
                draft.status = PublishDraftStatus.NEEDS_ATTENTION
            elif latest.status == PublishAttemptStatus.RECONCILED:
                if latest.external_status in {ExternalPublicationStatus.FAILED, ExternalPublicationStatus.NOT_FOUND, ExternalPublicationStatus.REMOVED}:
                    draft.status = PublishDraftStatus.FAILED
                else:
                    draft.status = PublishDraftStatus.NEEDS_ATTENTION
            elif latest.status == PublishAttemptStatus.FAILED:
                draft.status = PublishDraftStatus.FAILED
            else:
                draft.status = PublishDraftStatus.READY
        else:
            draft.current_publication_status = ExternalPublicationStatus.UNKNOWN
            draft.current_external_publish_id = None
            draft.current_external_permalink = None
            draft.published_at = None
            draft.last_publish_synced_at = None

        draft.publication_summary_json = self.build_publication_summary(draft, latest, canonical, attempts)
        draft.error_message = self._build_draft_error_message(latest, canonical)
        draft.updated_at = datetime.now(UTC)

    def build_publication_summary(
        self,
        draft: PublishDraft,
        latest: PublishAttempt | None,
        canonical: PublishAttempt | None,
        attempts: list[PublishAttempt],
    ) -> dict:
        duplicate_successes = [attempt for attempt in attempts if attempt.external_status == ExternalPublicationStatus.PUBLISHED]
        return {
            "publish_draft_id": str(draft.id),
            "canonical_publish_attempt_id": str(canonical.id) if canonical else None,
            "latest_publish_attempt_id": str(latest.id) if latest else None,
            "current_external_status": (canonical or latest).external_status.value if (canonical or latest) else ExternalPublicationStatus.UNKNOWN.value,
            "current_external_publish_id": (canonical or latest).external_publish_id if (canonical or latest) else None,
            "current_external_permalink": (canonical or latest).external_permalink if (canonical or latest) else None,
            "last_checked_at": ((canonical or latest).last_status_checked_at or (canonical or latest).finished_at).isoformat() if (canonical or latest) and ((canonical or latest).last_status_checked_at or (canonical or latest).finished_at) else None,
            "canonical_success": canonical is not None,
            "duplicate_success_count": max(len(duplicate_successes) - 1, 0),
        }

    def apply_success(self, attempt: PublishAttempt) -> None:
        attempt.reconciliation_required = False
        attempt.reconciliation_status = PublishReconciliationStatus.NOT_REQUIRED
        attempt.status = PublishAttemptStatus.SUCCEEDED
        attempt.finished_at = attempt.finished_at or datetime.now(UTC)

    def apply_uncertain_failure(self, attempt: PublishAttempt, *, error_code: str | None, error_message: str | None) -> None:
        attempt.error_code = error_code
        attempt.error_message = error_message
        attempt.finished_at = datetime.now(UTC)
        if attempt.external_publish_id or attempt.external_media_id or attempt.external_reel_id:
            attempt.status = PublishAttemptStatus.NEEDS_RECONCILIATION
            attempt.reconciliation_required = True
            attempt.reconciliation_status = PublishReconciliationStatus.REQUIRED
        else:
            attempt.status = PublishAttemptStatus.FAILED
            attempt.reconciliation_required = False
            attempt.reconciliation_status = PublishReconciliationStatus.RESOLVED_FAILURE

    def mark_reconciled(self, attempt: PublishAttempt, external_status: ExternalPublicationStatus) -> None:
        attempt.external_status = external_status
        attempt.last_status_checked_at = datetime.now(UTC)
        attempt.reconciliation_required = external_status not in {ExternalPublicationStatus.PUBLISHED, ExternalPublicationStatus.FAILED, ExternalPublicationStatus.NOT_FOUND}
        if external_status == ExternalPublicationStatus.PUBLISHED:
            attempt.status = PublishAttemptStatus.RECONCILED
            attempt.reconciliation_status = PublishReconciliationStatus.RESOLVED_SUCCESS
        elif external_status in {ExternalPublicationStatus.FAILED, ExternalPublicationStatus.NOT_FOUND}:
            attempt.status = PublishAttemptStatus.RECONCILED
            attempt.reconciliation_status = PublishReconciliationStatus.RESOLVED_FAILURE
        else:
            attempt.status = PublishAttemptStatus.NEEDS_RECONCILIATION
            attempt.reconciliation_status = PublishReconciliationStatus.UNRESOLVED

    def _select_canonical_attempt(self, attempts: list[PublishAttempt]) -> PublishAttempt | None:
        published_attempts = [attempt for attempt in attempts if attempt.external_status == ExternalPublicationStatus.PUBLISHED]
        if published_attempts:
            return sorted(
                published_attempts,
                key=lambda item: (
                    item.finished_at or item.last_status_checked_at or item.created_at,
                    item.attempt_number,
                ),
                reverse=True,
            )[0]
        succeeded_attempts = [
            attempt
            for attempt in attempts
            if attempt.status in {PublishAttemptStatus.SUCCEEDED, PublishAttemptStatus.RECONCILED}
            and attempt.external_status == ExternalPublicationStatus.PUBLISHED
        ]
        if succeeded_attempts:
            return sorted(succeeded_attempts, key=lambda item: (item.finished_at or item.created_at, item.attempt_number), reverse=True)[0]
        return None

    def _build_draft_error_message(self, latest: PublishAttempt | None, canonical: PublishAttempt | None) -> str | None:
        if canonical is not None:
            return None
        if latest is None:
            return None
        if latest.status in {PublishAttemptStatus.NEEDS_RECONCILIATION, PublishAttemptStatus.RECONCILING}:
            return "Latest publish attempt needs reconciliation."
        return latest.error_message
