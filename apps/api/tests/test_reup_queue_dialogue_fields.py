"""Reup Queue item response exposes dialogue/speech summary for worklist CTAs."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.api.routes.reup_queue import _queue_item_response
from src.enums import JobStatus, ReupQueueMediaPrepStatus, ReupQueueStatus


def _base_item(**overrides):
    defaults = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "video_candidate_id": uuid4(),
        "source_video_id": uuid4(),
        "status": ReupQueueStatus.WAITING_FOR_METADATA,
        "priority": 100,
        "queued_reason": "review_board_approved",
        "operator_note": None,
        "last_error_code": None,
        "last_error_message": None,
        "media_prep_status": ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        "media_prep_notes": None,
        "media_ready_at": None,
        "blocked_reason": None,
        "blocked_at": None,
        "held_at": None,
        "failed_at": None,
        "last_action": None,
        "last_action_at": None,
        "last_action_note": None,
        "queued_at": datetime.now(UTC),
        "started_at": datetime.now(UTC),
        "completed_at": None,
        "cancelled_at": None,
        "operator_dismissed_at": None,
        "job_id": uuid4(),
        "job": None,
        "render_output_id": None,
        "publish_draft_id": None,
        "metadata_json": None,
        "source_video": None,
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReupQueueDialogueFieldsTests(unittest.TestCase):
    def test_queue_item_response_includes_no_dialogue_summary(self) -> None:
        job = SimpleNamespace(
            id=uuid4(),
            job_type="ANALYZE_AUDIO",
            status=JobStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
        )
        source_video = SimpleNamespace(
            id=uuid4(),
            source_profile_id=uuid4(),
            source_video_external_id="x",
            source_url="https://example.com/v",
            caption="title not dialogue",
            posted_at=None,
            duration_seconds=51.0,
            metadata_json={
                "has_speech": False,
                "dialogue_phase": "no_dialogue",
                "transcript_count": 0,
            },
        )
        item = _base_item(job=job, job_id=job.id, source_video=source_video)
        response = _queue_item_response(item)
        self.assertEqual(response.dialogue_phase, "no_dialogue")
        self.assertEqual(response.has_speech, False)
        self.assertEqual(response.transcript_count, 0)

    def test_queue_item_response_includes_dialogue_beats_summary(self) -> None:
        job = SimpleNamespace(
            id=uuid4(),
            job_type="ANALYZE_AUDIO",
            status=JobStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
        )
        source_video = SimpleNamespace(
            id=uuid4(),
            source_profile_id=uuid4(),
            source_video_external_id="y",
            source_url="https://example.com/v2",
            caption="口播",
            posted_at=None,
            duration_seconds=20.0,
            metadata_json={
                "has_speech": True,
                "dialogue_phase": "source_auto_approved",
                "transcript_count": 3,
            },
        )
        item = _base_item(job=job, job_id=job.id, source_video=source_video)
        response = _queue_item_response(item)
        self.assertEqual(response.dialogue_phase, "source_auto_approved")
        self.assertEqual(response.has_speech, True)
        self.assertEqual(response.transcript_count, 3)


if __name__ == "__main__":
    unittest.main()
