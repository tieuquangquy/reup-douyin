from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import unittest
from uuid import uuid4

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishDraftStatus, PublishReconciliationStatus
from src.publish.services.publish_reconciliation_service import PublishReconciliationService


def _attempt(**overrides):
    defaults = {
        "id": uuid4(),
        "status": PublishAttemptStatus.RUNNING,
        "started_at": datetime.now(UTC) - timedelta(hours=3),
        "created_at": datetime.now(UTC) - timedelta(hours=3),
        "external_publish_id": None,
        "external_media_id": None,
        "external_reel_id": None,
        "external_status": ExternalPublicationStatus.UNKNOWN,
        "reconciliation_required": False,
        "reconciliation_status": PublishReconciliationStatus.NOT_REQUIRED,
        "error_code": None,
        "error_message": None,
        "finished_at": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class PublishReconciliationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = object.__new__(PublishReconciliationService)

    def test_stale_active_attempt_with_external_reference_needs_reconciliation(self) -> None:
        attempt = _attempt(external_publish_id="video-123")

        self.assertTrue(PublishReconciliationService._is_stale_active_attempt(self.service, attempt))
        PublishReconciliationService._mark_stale_attempt(self.service, attempt)

        self.assertEqual(attempt.status, PublishAttemptStatus.NEEDS_RECONCILIATION)
        self.assertTrue(attempt.reconciliation_required)
        self.assertEqual(attempt.reconciliation_status, PublishReconciliationStatus.REQUIRED)
        self.assertEqual(attempt.error_code, "stale_attempt_state")

    def test_stale_active_attempt_without_external_reference_fails(self) -> None:
        attempt = _attempt()

        PublishReconciliationService._mark_stale_attempt(self.service, attempt)

        self.assertEqual(attempt.status, PublishAttemptStatus.FAILED)
        self.assertFalse(attempt.reconciliation_required)
        self.assertEqual(attempt.reconciliation_status, PublishReconciliationStatus.RESOLVED_FAILURE)
        self.assertIsNotNone(attempt.finished_at)

    def test_warning_summary_flags_duplicate_and_ambiguous_statuses(self) -> None:
        draft = SimpleNamespace(status=PublishDraftStatus.NEEDS_ATTENTION)
        attempts = [
            _attempt(status=PublishAttemptStatus.RECONCILED, external_status=ExternalPublicationStatus.PUBLISHED),
            _attempt(status=PublishAttemptStatus.SUCCEEDED, external_status=ExternalPublicationStatus.PUBLISHED),
            _attempt(status=PublishAttemptStatus.NEEDS_RECONCILIATION, external_status=ExternalPublicationStatus.PARTIALLY_CONFIRMED),
        ]

        warnings = PublishReconciliationService._build_warnings(self.service, draft, attempts, duplicate_success_count=1)

        self.assertIn("latest_publish_state_needs_operator_attention", warnings)
        self.assertIn("attempt_needs_reconciliation", warnings)
        self.assertIn("duplicate_successful_publish_attempts", warnings)
        self.assertIn("ambiguous_platform_status_present", warnings)


if __name__ == "__main__":
    unittest.main()
