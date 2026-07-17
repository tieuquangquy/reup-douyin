"""Promoted Capture Inbox items must remain discoverable when their Review Board row was archived."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.enums import CandidateStatus, CapturedItemStatus
from src.services import capture_inbox_service, candidate_service
from src.services.capture_inbox_service import CaptureInboxService
from src.services.candidate_service import CandidateEvaluationService


class CaptureInboxPromoteReactivateArchivedTests(unittest.TestCase):
    def test_search_filter_includes_archived_candidates(self) -> None:
        source = inspect.getsource(candidate_service.CandidateEvaluationService._apply_candidate_list_filters)
        self.assertIn("search_term", source)
        self.assertIn("not search_term", source)
        self.assertIn("CandidateStatus.ARCHIVED", source)

    def test_reactivate_for_review_board_restores_shortlisted_status(self) -> None:
        candidate = SimpleNamespace(
            status=CandidateStatus.ARCHIVED,
            metadata_json={
                "removed_from_review_board": True,
                "removed_from_review_board_at": "2026-01-01T00:00:00Z",
                "removed_from_review_board_reason": "operator_delete",
                "aweme_id": "7658958713592992100",
            },
        )
        service = CandidateEvaluationService(SimpleNamespace())  # type: ignore[arg-type]
        changed = service.reactivate_for_review_board(candidate)  # type: ignore[arg-type]

        self.assertTrue(changed)
        self.assertEqual(candidate.status, CandidateStatus.SHORTLISTED)
        self.assertNotIn("removed_from_review_board", candidate.metadata_json)

    def test_promotion_skip_allows_repromote_when_linked_candidate_archived(self) -> None:
        candidate_id = uuid4()
        item = SimpleNamespace(
            status=CapturedItemStatus.PROMOTED,
            promoted_video_candidate_id=candidate_id,
        )
        db = SimpleNamespace(
            get=lambda _model, _id: SimpleNamespace(id=candidate_id, status=CandidateStatus.ARCHIVED)
        )
        service = CaptureInboxService(db)  # type: ignore[arg-type]
        reason = service._promotion_skip_reason(item, allowed_statuses=set())  # type: ignore[arg-type]
        self.assertIsNone(reason)

    def test_mark_item_promoted_reactivates_archived_candidate(self) -> None:
        source = inspect.getsource(capture_inbox_service.CaptureInboxService._mark_item_promoted_to_review_board)
        self.assertIn("reactivate_for_review_board", source)
