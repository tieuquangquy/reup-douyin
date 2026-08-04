from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.api.routes.reup_queue import _queue_item_response
from src.enums import ReupQueueMediaPrepStatus, ReupQueueStatus


class ReupQueueEnqueueResponseTests(unittest.TestCase):
    def test_queue_item_response_serializes_available_actions_for_enqueue_items(self) -> None:
        item = SimpleNamespace(
            id=uuid4(),
            workspace_id=uuid4(),
            video_candidate_id=uuid4(),
            source_video_id=uuid4(),
            status=ReupQueueStatus.READY_FOR_PROCESSING,
            priority=100,
            queued_reason="review_board_approved",
            operator_note=None,
            last_error_code=None,
            last_error_message=None,
            media_prep_status=ReupQueueMediaPrepStatus.NOT_STARTED,
            media_prep_notes=None,
            media_ready_at=None,
            blocked_reason=None,
            blocked_at=None,
            held_at=None,
            failed_at=None,
            last_action=None,
            last_action_at=None,
            last_action_note=None,
            queued_at=datetime.now(UTC),
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            operator_dismissed_at=None,
            job_id=None,
            render_output_id=None,
            publish_draft_id=None,
            metadata_json={"source": "review_board"},
            source_video=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        response = _queue_item_response(item)

        self.assertEqual(response.status, ReupQueueStatus.READY_FOR_PROCESSING)
        self.assertGreater(len(response.available_actions), 0)
        self.assertIn("Start processing", [action.label for action in response.available_actions])


if __name__ == "__main__":
    unittest.main()
