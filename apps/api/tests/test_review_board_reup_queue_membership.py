from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.enums import CandidateStatus, ReupQueueStatus
from src.schemas.candidates import CandidateSummaryResponse
from src.services.reup_queue_service import ReupQueueCandidateMembership, ReupQueueService, is_active_reup_queue_status


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def unique(self):
        return self.values


class FakeMembershipDb:
    def __init__(self, items):
        self._items = items

    def scalars(self, _stmt):
        return FakeScalarResult(self._items)


class ReviewBoardReupQueueMembershipTests(unittest.TestCase):
    def test_membership_lookup_marks_candidates_already_in_queue(self) -> None:
        candidate_id = uuid4()
        item_id = uuid4()
        item = SimpleNamespace(
            id=item_id,
            video_candidate_id=candidate_id,
            status=ReupQueueStatus.READY_FOR_PROCESSING,
        )
        memberships = ReupQueueService(FakeMembershipDb([item])).membership_for_candidates([candidate_id, uuid4()])

        self.assertTrue(memberships[candidate_id].in_reup_queue)
        self.assertEqual(memberships[candidate_id].reup_queue_item_id, item_id)
        self.assertEqual(memberships[candidate_id].reup_queue_status, ReupQueueStatus.READY_FOR_PROCESSING)
        missing = [key for key, value in memberships.items() if key != candidate_id][0]
        self.assertFalse(memberships[missing].in_reup_queue)

    def test_membership_does_not_mark_cancelled_candidates_as_in_queue(self) -> None:
        candidate_id = uuid4()
        item = SimpleNamespace(
            id=uuid4(),
            video_candidate_id=candidate_id,
            status=ReupQueueStatus.CANCELLED,
        )
        memberships = ReupQueueService(FakeMembershipDb([item])).membership_for_candidates([candidate_id])

        self.assertFalse(memberships[candidate_id].in_reup_queue)
        self.assertEqual(memberships[candidate_id].reup_queue_status, ReupQueueStatus.CANCELLED)

    def test_membership_does_not_mark_completed_candidates_as_in_queue(self) -> None:
        candidate_id = uuid4()
        item = SimpleNamespace(
            id=uuid4(),
            video_candidate_id=candidate_id,
            status=ReupQueueStatus.COMPLETED,
        )
        memberships = ReupQueueService(FakeMembershipDb([item])).membership_for_candidates([candidate_id])

        self.assertFalse(memberships[candidate_id].in_reup_queue)
        self.assertTrue(is_active_reup_queue_status(ReupQueueStatus.READY_FOR_PROCESSING))
        self.assertFalse(is_active_reup_queue_status(ReupQueueStatus.COMPLETED))

    def test_candidate_summary_exposes_reup_queue_membership(self) -> None:
        candidate_id = uuid4()
        candidate = SimpleNamespace(
            id=candidate_id,
            source_video_id=uuid4(),
            status=CandidateStatus.APPROVED,
            score=80.0,
            score_label="hot",
            priority=80,
            preset_name="viral_discovery",
            metadata_json={},
            evaluated_at=None,
            updated_at=datetime(2026, 4, 1, tzinfo=UTC),
            source_video=None,
        )
        membership = ReupQueueCandidateMembership(
            in_reup_queue=True,
            reup_queue_item_id=uuid4(),
            reup_queue_status=ReupQueueStatus.READY_FOR_PROCESSING,
        )

        summary = CandidateSummaryResponse.from_candidate(candidate, reup_queue_membership=membership)

        self.assertTrue(summary.in_reup_queue)
        self.assertEqual(summary.reup_queue_status, ReupQueueStatus.READY_FOR_PROCESSING.value)

    def test_candidate_detail_exposes_the_same_reup_queue_membership(self) -> None:
        from src.api.routes.candidates import _candidate_detail_response

        candidate_id = uuid4()
        item_id = uuid4()
        timestamp = datetime(2026, 4, 1, tzinfo=UTC)
        candidate = SimpleNamespace(
            id=candidate_id,
            source_video_id=uuid4(),
            status=CandidateStatus.APPROVED,
            score=75.0,
            score_version="v1",
            score_label="strong",
            score_breakdown_json={},
            score_reason=None,
            preset_name="viral_discovery",
            filter_config_json=None,
            inclusion_reasons_json=[],
            exclusion_reasons_json=[],
            warnings_json=[],
            evaluated_at=timestamp,
            priority=75,
            metadata_json={},
            created_at=timestamp,
            updated_at=timestamp,
            source_video=None,
        )
        membership = ReupQueueCandidateMembership(
            in_reup_queue=True,
            reup_queue_item_id=item_id,
            reup_queue_status=ReupQueueStatus.READY_FOR_PROCESSING,
        )

        detail = _candidate_detail_response(candidate, reup_queue_membership=membership)

        self.assertTrue(detail.in_reup_queue)
        self.assertEqual(detail.reup_queue_item_id, item_id)
        self.assertEqual(detail.reup_queue_status, ReupQueueStatus.READY_FOR_PROCESSING.value)


if __name__ == "__main__":
    unittest.main()
