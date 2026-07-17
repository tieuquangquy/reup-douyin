from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
import unittest
from uuid import uuid4

from src.enums import CandidateStatus, ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_queue_service import available_actions_for_item, bucket_for_status, next_action_for_status


class FakeScalarResult:
    def __init__(self, values):
        self.values = values

    def unique(self):
        return self.values


class FakeDb:
    def __init__(self, candidates, existing_items):
        self._candidates = candidates
        self._existing_items = existing_items
        self.added = []
        self.committed = False
        self.refreshed = []
        self.scalars_calls = 0

    def scalars(self, _stmt):
        self.scalars_calls += 1
        if self.scalars_calls == 1:
            return FakeScalarResult(self._candidates)
        return FakeScalarResult(self._existing_items)

    def add(self, item):
        self.added.append(item)

    def commit(self):
        self.committed = True

    def refresh(self, item):
        self.refreshed.append(item)


class FakeActionDb:
    def __init__(self, item):
        self.item = item
        self.committed = False
        self.refreshed = []

    def scalar(self, _stmt):
        return self.item

    def get(self, _model, _job_id):
        return None

    def commit(self):
        self.committed = True

    def refresh(self, item):
        self.refreshed.append(item)


def queue_item(**overrides):
    item_id = uuid4()
    defaults = {
        "id": item_id,
        "workspace_id": uuid4(),
        "video_candidate_id": uuid4(),
        "source_video_id": uuid4(),
        "status": ReupQueueStatus.READY_FOR_PROCESSING,
        "media_prep_status": ReupQueueMediaPrepStatus.NOT_STARTED,
        "media_prep_notes": None,
        "media_ready_at": None,
        "blocked_reason": None,
        "blocked_at": None,
        "held_at": None,
        "failed_at": None,
        "last_action": None,
        "last_action_at": None,
        "last_action_note": None,
        "last_error_code": None,
        "last_error_message": None,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "job_id": None,
        "metadata_json": None,
        "source_video": None,
        "video_candidate": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReupQueueServiceTests(unittest.TestCase):
    def test_status_projection_has_operator_bucket_and_next_action(self) -> None:
        self.assertEqual(bucket_for_status(ReupQueueStatus.READY_FOR_PROCESSING), "Ready for processing")
        self.assertIn("Start downstream processing", next_action_for_status(ReupQueueStatus.READY_FOR_PROCESSING))
        self.assertEqual(bucket_for_status(ReupQueueStatus.FAILED_NEEDS_ATTENTION), "Failed / needs attention")

    def test_available_actions_are_state_aware(self) -> None:
        ready = queue_item(status=ReupQueueStatus.READY_FOR_PROCESSING)
        ready_actions = {action.action for action in available_actions_for_item(ready)}
        self.assertIn(ReupQueueAction.START_PROCESSING, ready_actions)
        self.assertIn(ReupQueueAction.HOLD, ready_actions)
        self.assertNotIn(ReupQueueAction.RETRY, ready_actions)

        failed = queue_item(status=ReupQueueStatus.FAILED_NEEDS_ATTENTION, media_prep_status=ReupQueueMediaPrepStatus.BLOCKED)
        failed_actions = {action.action for action in available_actions_for_item(failed)}
        self.assertEqual(
            failed_actions,
            {ReupQueueAction.RETRY, ReupQueueAction.RESUME, ReupQueueAction.CANCEL, ReupQueueAction.DISMISS},
        )

    def test_apply_action_marks_media_ready_for_export_handoff(self) -> None:
        from src.services.reup_queue_service import ReupQueueService

        item = queue_item(status=ReupQueueStatus.PROCESSING, started_at=datetime(2026, 4, 27, tzinfo=UTC))
        fake_db = FakeActionDb(item)
        analyze_job_id = uuid4()

        class _FakeAnalysis:
            def create_analysis_job(self, request, *, idempotency_key=None):
                return SimpleNamespace(id=analyze_job_id, job_type="ANALYZE_AUDIO")

        updated = ReupQueueService(fake_db, audio_analysis_service=_FakeAnalysis()).apply_action(
            item.id,
            action=ReupQueueAction.MARK_MEDIA_READY,
            note="media confirmed",
            media_prep_notes="source media available",
            media_prep_status=ReupQueueMediaPrepStatus.READY_FOR_EXPORT,
        )

        self.assertTrue(fake_db.committed)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.media_prep_status, ReupQueueMediaPrepStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.media_prep_notes, "source media available")
        self.assertIsNotNone(updated.media_ready_at)
        self.assertEqual(updated.last_action, ReupQueueAction.MARK_MEDIA_READY)
        self.assertEqual(updated.job_id, analyze_job_id)

    def test_apply_action_records_blocked_reason_and_failure_state(self) -> None:
        from src.services.reup_queue_service import ReupQueueService

        item = queue_item(status=ReupQueueStatus.PROCESSING)
        updated = ReupQueueService(FakeActionDb(item)).apply_action(
            item.id,
            action=ReupQueueAction.MARK_BLOCKED,
            blocked_reason="Source media unavailable",
        )

        self.assertEqual(updated.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)
        self.assertEqual(updated.media_prep_status, ReupQueueMediaPrepStatus.BLOCKED)
        self.assertEqual(updated.blocked_reason, "Source media unavailable")
        self.assertEqual(updated.last_error_code, "OPERATOR_BLOCKED")
        self.assertIsNotNone(updated.failed_at)

    def test_enqueue_only_approved_candidates_and_is_idempotent(self) -> None:
        approved_id = uuid4()
        rejected_id = uuid4()
        existing_id = uuid4()
        workspace_id = uuid4()
        approved = SimpleNamespace(
            id=approved_id,
            workspace_id=workspace_id,
            source_video_id=uuid4(),
            status=CandidateStatus.APPROVED,
            source_video=None,
        )
        rejected = SimpleNamespace(
            id=rejected_id,
            workspace_id=workspace_id,
            source_video_id=uuid4(),
            status=CandidateStatus.REJECTED,
            source_video=None,
        )
        existing_candidate = SimpleNamespace(
            id=existing_id,
            workspace_id=workspace_id,
            source_video_id=uuid4(),
            status=CandidateStatus.APPROVED,
            source_video=None,
        )
        existing_item = SimpleNamespace(
            id=uuid4(),
            video_candidate_id=existing_id,
            status=ReupQueueStatus.READY_FOR_PROCESSING,
            queued_at=datetime(2026, 4, 27, tzinfo=UTC),
            source_video=None,
            video_candidate=existing_candidate,
        )
        fake_db = FakeDb([approved, rejected, existing_candidate], [existing_item])

        from src.services.reup_queue_service import ReupQueueService

        result = ReupQueueService(fake_db).enqueue_candidates(candidate_ids=[approved_id, rejected_id, existing_id], priority=25)

        self.assertTrue(fake_db.committed)
        self.assertEqual(result.requested_count, 3)
        self.assertEqual(result.queued_count, 1)
        self.assertEqual(result.already_queued_count, 1)
        self.assertEqual(result.skipped_count, 1)
        self.assertEqual(result.skipped_candidate_ids, [rejected_id])
        self.assertEqual(len(fake_db.added), 1)
        created = fake_db.added[0]
        self.assertEqual(created.workspace_id, workspace_id)
        self.assertEqual(created.video_candidate_id, approved_id)
        self.assertEqual(created.status, ReupQueueStatus.READY_FOR_PROCESSING)
        self.assertEqual(created.media_prep_status, ReupQueueMediaPrepStatus.NOT_STARTED)
        self.assertEqual(created.priority, 25)

    def test_enqueue_reactivates_cancelled_queue_item_for_same_candidate(self) -> None:
        candidate_id = uuid4()
        workspace_id = uuid4()
        candidate = SimpleNamespace(
            id=candidate_id,
            workspace_id=workspace_id,
            source_video_id=uuid4(),
            status=CandidateStatus.APPROVED,
            source_video=None,
        )
        existing_item = SimpleNamespace(
            id=uuid4(),
            video_candidate_id=candidate_id,
            workspace_id=workspace_id,
            source_video_id=candidate.source_video_id,
            status=ReupQueueStatus.CANCELLED,
            media_prep_status=ReupQueueMediaPrepStatus.NOT_STARTED,
            priority=10,
            queued_at=datetime(2026, 4, 1, tzinfo=UTC),
            cancelled_at=datetime(2026, 4, 2, tzinfo=UTC),
            job_id=uuid4(),
            source_video=None,
            video_candidate=candidate,
        )
        fake_db = FakeDb([candidate], [existing_item])

        from src.services.reup_queue_service import ReupQueueService

        result = ReupQueueService(fake_db).enqueue_candidates(candidate_ids=[candidate_id], priority=25)

        self.assertTrue(fake_db.committed)
        self.assertEqual(result.queued_count, 1)
        self.assertEqual(result.already_queued_count, 0)
        self.assertEqual(len(fake_db.added), 0)
        self.assertEqual(existing_item.status, ReupQueueStatus.READY_FOR_PROCESSING)
        self.assertIsNone(existing_item.cancelled_at)
        self.assertIsNone(existing_item.job_id)
        self.assertEqual(existing_item.priority, 25)


if __name__ == "__main__":
    unittest.main()
