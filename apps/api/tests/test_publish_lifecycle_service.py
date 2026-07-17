from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from uuid import uuid4

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishDraftStatus, PublishReconciliationStatus
from src.publish.services.publish_lifecycle_service import PublishLifecycleService


def _attempt(**overrides):
    defaults = {
        "id": uuid4(),
        "status": PublishAttemptStatus.FAILED,
        "external_status": ExternalPublicationStatus.UNKNOWN,
        "external_publish_id": None,
        "external_reel_id": None,
        "external_permalink": None,
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "finished_at": None,
        "last_status_checked_at": None,
        "attempt_number": 1,
        "error_message": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class PublishLifecycleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = PublishLifecycleService(db=None)  # type: ignore[arg-type]

    def test_uncertain_failure_with_external_reference_requires_reconciliation(self) -> None:
        attempt = _attempt(external_publish_id="video-123")

        self.service.apply_uncertain_failure(attempt, error_code="network_request_failed", error_message="network lost")

        self.assertEqual(attempt.status, PublishAttemptStatus.NEEDS_RECONCILIATION)
        self.assertTrue(attempt.reconciliation_required)
        self.assertEqual(attempt.reconciliation_status, PublishReconciliationStatus.REQUIRED)

    def test_mark_reconciled_published_selects_canonical_draft_attempt(self) -> None:
        draft = SimpleNamespace(
            id=uuid4(),
            latest_publish_attempt_id=None,
            canonical_publish_attempt_id=None,
            current_publication_status=ExternalPublicationStatus.UNKNOWN,
            current_external_publish_id=None,
            current_external_permalink=None,
            published_at=None,
            last_publish_synced_at=None,
            publication_summary_json=None,
            error_message=None,
            status=PublishDraftStatus.READY,
            updated_at=None,
        )
        attempt = _attempt(
            status=PublishAttemptStatus.NEEDS_RECONCILIATION,
            external_publish_id="video-123",
            external_status=ExternalPublicationStatus.UNKNOWN,
            external_permalink="https://facebook.com/reel/video-123",
        )

        self.service.mark_reconciled(attempt, ExternalPublicationStatus.PUBLISHED)
        self.service.sync_attempt_to_draft(draft, [attempt])

        self.assertEqual(attempt.status, PublishAttemptStatus.RECONCILED)
        self.assertEqual(attempt.reconciliation_status, PublishReconciliationStatus.RESOLVED_SUCCESS)
        self.assertEqual(draft.status, PublishDraftStatus.PUBLISHED)
        self.assertEqual(draft.canonical_publish_attempt_id, attempt.id)
        self.assertEqual(draft.current_external_publish_id, "video-123")

    def test_reconciled_failure_does_not_become_canonical_success(self) -> None:
        draft = SimpleNamespace(
            id=uuid4(),
            latest_publish_attempt_id=None,
            canonical_publish_attempt_id=None,
            current_publication_status=ExternalPublicationStatus.UNKNOWN,
            current_external_publish_id=None,
            current_external_permalink=None,
            published_at=None,
            last_publish_synced_at=None,
            publication_summary_json=None,
            error_message=None,
            status=PublishDraftStatus.READY,
            updated_at=None,
        )
        attempt = _attempt(
            status=PublishAttemptStatus.RECONCILED,
            external_publish_id="video-123",
            external_status=ExternalPublicationStatus.FAILED,
            reconciliation_status=PublishReconciliationStatus.RESOLVED_FAILURE,
            error_message="Platform reports failure.",
        )

        self.service.sync_attempt_to_draft(draft, [attempt])

        self.assertEqual(draft.status, PublishDraftStatus.FAILED)
        self.assertIsNone(draft.canonical_publish_attempt_id)
        self.assertEqual(draft.current_publication_status, ExternalPublicationStatus.FAILED)


if __name__ == "__main__":
    unittest.main()
