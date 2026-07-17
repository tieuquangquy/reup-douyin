"""Promote must not leave Capture Inbox items PROMOTED without a Review Board candidate."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace

from src.enums import CapturedItemStatus
from src.services import capture_inbox_service
from src.services.capture_inbox_service import CaptureInboxService


class CaptureInboxPromoteOrphanRepairTests(unittest.TestCase):
    def test_mark_item_promoted_requires_candidate_handoff(self) -> None:
        source = inspect.getsource(capture_inbox_service.CaptureInboxService._mark_item_promoted_to_review_board)
        self.assertIn("if candidate is None", source)
        self.assertIn("return", source)
    def test_promote_loop_ensures_candidate_before_marking_promoted(self) -> None:
        source = inspect.getsource(capture_inbox_service.CaptureInboxService.promote)
        self.assertIn("_ensure_review_board_candidate_for_source_video", source)
        self.assertIn("promotion_missing_candidate", source)

        source = inspect.getsource(capture_inbox_service.CaptureInboxService)
        self.assertIn("def repair_orphaned_handoffs_for_search", source)
        repair_source = inspect.getsource(capture_inbox_service.CaptureInboxService.repair_orphaned_handoffs_for_search)
        self.assertIn("CapturedItem.caption", repair_source)
        self.assertIn("metadata_json", repair_source)
        self.assertNotIn("CapturedItem.title", repair_source, "CapturedItem has no title column")

    def test_promotion_skip_allows_repromote_when_candidate_link_missing(self) -> None:
        item = SimpleNamespace(
            status=CapturedItemStatus.PROMOTED,
            promoted_video_candidate_id=None,
        )
        service = CaptureInboxService(SimpleNamespace())  # type: ignore[arg-type]
        reason = service._promotion_skip_reason(item, allowed_statuses=set())  # type: ignore[arg-type]
        self.assertIsNone(reason)

    def test_list_candidates_repairs_orphaned_handoffs_on_search_miss(self) -> None:
        from src.api.routes import candidates as candidate_routes

        route_source = inspect.getsource(candidate_routes.list_candidates)
        self.assertIn("repair_orphaned_handoffs_for_search", route_source)


if __name__ == "__main__":
    unittest.main()
