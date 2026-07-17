from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from src.enums import ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.download_service import DownloadJobResult
from src.services.reup_queue_service import ReupQueueService


class FakeActionDb:
    def __init__(self, item):
        self.item = item
        self.committed = False
        self.refreshed = []

    def scalar(self, _stmt):
        return self.item

    def commit(self):
        self.committed = True

    def refresh(self, item):
        self.refreshed.append(item)


class FakeDownloadService:
    def __init__(self):
        self.calls: list[dict] = []

    def create_download_job(self, request, *, idempotency_key: str | None = None):
        self.calls.append(
            {
                "source_video_id": request.source_video_id,
                "candidate_id": request.candidate_id,
                "force_refresh": getattr(request, "force_refresh", False),
                "idempotency_key": idempotency_key,
            }
        )
        return DownloadJobResult(
            job_id=str(uuid4()),
            status="QUEUED",
            source_video_id=str(request.source_video_id),
            asset_count=0,
            manifest={"assets": []},
        )


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
        "source_video": None,
        "video_candidate": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReupQueueStartProcessingDownloadTests(unittest.TestCase):
    def test_start_processing_creates_download_job_and_moves_to_waiting_for_media(self) -> None:
        item = queue_item(status=ReupQueueStatus.READY_FOR_PROCESSING)
        download_service = FakeDownloadService()
        updated = ReupQueueService(FakeActionDb(item), download_service=download_service).apply_action(
            item.id,
            action=ReupQueueAction.START_PROCESSING,
        )

        self.assertEqual(len(download_service.calls), 1)
        self.assertEqual(download_service.calls[0]["idempotency_key"], f"reup-queue:{item.id}:download")
        self.assertTrue(download_service.calls[0]["force_refresh"])
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_MEDIA)
        self.assertEqual(updated.media_prep_status, ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA)
        self.assertIsNotNone(updated.job_id)
        self.assertIsNotNone(updated.started_at)

    def test_start_processing_reuses_existing_job_id(self) -> None:
        existing_job_id = uuid4()
        item = queue_item(status=ReupQueueStatus.READY_FOR_PROCESSING, job_id=existing_job_id)
        download_service = FakeDownloadService()
        updated = ReupQueueService(FakeActionDb(item), download_service=download_service).apply_action(
            item.id,
            action=ReupQueueAction.START_PROCESSING,
        )

        self.assertEqual(download_service.calls, [])
        self.assertEqual(updated.job_id, existing_job_id)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_MEDIA)

    def test_retry_clears_job_id_for_fresh_download(self) -> None:
        item = queue_item(status=ReupQueueStatus.FAILED_NEEDS_ATTENTION, job_id=uuid4())
        updated = ReupQueueService(FakeActionDb(item)).apply_action(item.id, action=ReupQueueAction.RETRY)
        self.assertEqual(updated.status, ReupQueueStatus.READY_FOR_PROCESSING)
        self.assertIsNone(updated.job_id)


if __name__ == "__main__":
    unittest.main()
