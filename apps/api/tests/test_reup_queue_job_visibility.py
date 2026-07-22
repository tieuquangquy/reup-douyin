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
        "status": ReupQueueStatus.WAITING_FOR_MEDIA,
        "priority": 100,
        "queued_reason": "review_board_approved",
        "operator_note": None,
        "last_error_code": None,
        "last_error_message": None,
        "media_prep_status": ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA,
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


class ReupQueueJobVisibilityResponseTests(unittest.TestCase):
    def test_queue_item_response_includes_job_progress_and_error_fields(self) -> None:
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.RUNNING,
            progress_percent=42,
            error_code=None,
            error_message=None,
        )
        item = _base_item(job_id=job_id, job=job)

        response = _queue_item_response(item)

        self.assertEqual(response.job_status, "RUNNING")
        self.assertEqual(response.job_progress_percent, 42)
        self.assertIsNone(response.job_error_code)
        self.assertIsNone(response.job_error_message)

    def test_queue_item_response_includes_job_error_when_failed(self) -> None:
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            status=JobStatus.FAILED,
            progress_percent=0,
            error_code="DOWNLOAD_VALIDATION_FAILED",
            error_message="Asset content is empty",
        )
        item = _base_item(job_id=job_id, job=job)

        response = _queue_item_response(item)

        self.assertEqual(response.job_status, "FAILED")
        self.assertEqual(response.job_progress_percent, 0)
        self.assertEqual(response.job_error_code, "DOWNLOAD_VALIDATION_FAILED")
        self.assertEqual(response.job_error_message, "Asset content is empty")

    def test_queue_item_response_includes_job_type_for_analyze_audio(self) -> None:
        job_id = uuid4()
        job = SimpleNamespace(
            id=job_id,
            job_type="ANALYZE_AUDIO",
            status=JobStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
        )
        item = _base_item(
            job_id=job_id,
            job=job,
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        )

        response = _queue_item_response(item)

        self.assertEqual(response.job_type, "ANALYZE_AUDIO")
        self.assertEqual(response.job_status, "COMPLETED")

    def test_queue_item_response_prefers_analyze_audio_job_over_stale_linked_job(self) -> None:
        stale_id = uuid4()
        analyze_id = uuid4()
        stale_job = SimpleNamespace(
            id=stale_id,
            job_type="DOWNLOAD_VIDEO",
            status=JobStatus.CANCELLED,
            progress_percent=0,
            error_code=None,
            error_message=None,
        )
        analyze_job = SimpleNamespace(
            id=analyze_id,
            job_type="ANALYZE_AUDIO",
            status=JobStatus.COMPLETED,
            progress_percent=100,
            error_code=None,
            error_message=None,
        )
        item = _base_item(
            job_id=stale_id,
            job=stale_job,
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
            metadata_json={"analyze_audio_job_id": str(analyze_id)},
        )

        response = _queue_item_response(item, display_job=analyze_job)

        self.assertEqual(response.job_id, analyze_id)
        self.assertEqual(response.job_type, "ANALYZE_AUDIO")
        self.assertEqual(response.job_status, "COMPLETED")


if __name__ == "__main__":
    unittest.main()
