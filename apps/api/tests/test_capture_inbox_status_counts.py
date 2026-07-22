from __future__ import annotations

import inspect
import unittest
from uuid import uuid4


class CaptureInboxStatusCountTests(unittest.TestCase):
    def test_item_list_returns_database_status_counts(self) -> None:
        from src.api.routes.capture_inbox import list_captured_items

        expected_counts = {
            "all": 369,
            "ready": 369,
            "promoted": 0,
            "duplicate": 0,
            "needs_action": 0,
            "failed": 0,
        }

        class FakeCaptureInboxService:
            def list_items(self, **kwargs):
                self.list_kwargs = kwargs
                return [], expected_counts["ready"]

            def count_items_by_studio_status(self, **kwargs):
                self.count_kwargs = kwargs
                return expected_counts

        service = FakeCaptureInboxService()
        response = list_captured_items(
            capture_session_id=uuid4(),
            profile_url=None,
            status=None,
            studio_status="ready",
            limit=100,
            offset=0,
            service=service,
        )

        self.assertEqual(response.total_count, 369)
        self.assertEqual(response.status_counts, expected_counts)
        self.assertEqual(service.list_kwargs["studio_status"], "ready")
        self.assertNotIn("studio_status", service.count_kwargs)

    def test_service_uses_one_semantic_predicate_for_counts_and_tiles(self) -> None:
        from src.services.capture_inbox_service import CaptureInboxService

        list_source = inspect.getsource(CaptureInboxService.list_items)
        count_source = inspect.getsource(CaptureInboxService.count_items_by_studio_status)
        predicate_source = inspect.getsource(CaptureInboxService._studio_status_clause)

        self.assertIn("_studio_status_clause(studio_status)", list_source)
        self.assertIn("_studio_status_clause", count_source)
        self.assertIn("CapturedItem.matches_intake.is_(True)", predicate_source)
        self.assertIn("IntakeEvaluationStatus.FILTERED_OUT", predicate_source)
        self.assertIn("IntakeEvaluationStatus.EVALUATION_ERROR", predicate_source)


if __name__ == "__main__":
    unittest.main()
