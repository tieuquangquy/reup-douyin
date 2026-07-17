from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_queue_service import ReupQueueService, available_action_values


class FakeActionDb:
    def __init__(self, item, job=None):
        self.item = item
        self.job = job
        self.committed = False
        self.refreshed = []

    def scalar(self, _stmt):
        return self.item

    def get(self, _model, entity_id):
        if self.job is not None and self.job.id == entity_id:
            return self.job
        return None

    def commit(self):
        self.committed = True

    def refresh(self, item):
        self.refreshed.append(item)


def queue_item(**overrides):
    defaults = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "video_candidate_id": uuid4(),
        "source_video_id": uuid4(),
        "status": ReupQueueStatus.WAITING_FOR_MEDIA,
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
        "last_error_code": None,
        "last_error_message": None,
        "started_at": datetime(2026, 7, 14, tzinfo=UTC),
        "completed_at": None,
        "cancelled_at": None,
        "job_id": uuid4(),
        "source_video": None,
        "video_candidate": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class PauseDuringProgressTests(unittest.TestCase):
    def test_waiting_for_media_offers_hold_when_not_paused(self) -> None:
        item = queue_item(held_at=None)
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.HOLD, actions)
        self.assertNotIn(ReupQueueAction.RESUME, actions)

    def test_waiting_for_media_offers_resume_when_paused(self) -> None:
        item = queue_item(held_at=datetime(2026, 7, 14, tzinfo=UTC))
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.RESUME, actions)
        self.assertNotIn(ReupQueueAction.HOLD, actions)

    def test_hold_during_progress_cancels_job_and_sets_held(self) -> None:
        job_id = uuid4()
        item = queue_item(job_id=job_id, status=ReupQueueStatus.WAITING_FOR_MEDIA)
        fake_db = FakeActionDb(item)
        cancel = MagicMock(return_value=SimpleNamespace(id=job_id, status=JobStatus.CANCELLED))

        with patch("src.services.job_service.JobService") as job_service_cls:
            job_service_cls.return_value.cancel_job = cancel
            updated = ReupQueueService(fake_db).apply_action(
                item.id,
                action=ReupQueueAction.HOLD,
                note="Operator paused progress",
            )

        cancel.assert_called_once_with(job_id)
        self.assertIsNotNone(updated.held_at)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_MEDIA)
        self.assertIsNone(updated.blocked_reason)
        self.assertEqual(updated.last_action, ReupQueueAction.HOLD)

    def test_hold_frees_download_idempotency_key_for_resume(self) -> None:
        job_id = uuid4()
        item = queue_item(job_id=job_id, status=ReupQueueStatus.WAITING_FOR_MEDIA)
        logical_key = f"reup-queue:{item.id}:download"
        job = SimpleNamespace(id=job_id, status=JobStatus.RUNNING, idempotency_key=logical_key)
        fake_db = FakeActionDb(item, job=job)
        cancel = MagicMock(return_value=job)

        with patch("src.services.job_service.JobService") as job_service_cls:
            job_service_cls.return_value.cancel_job = cancel
            ReupQueueService(fake_db).apply_action(
                item.id,
                action=ReupQueueAction.HOLD,
                note="Operator paused progress",
            )

        cancel.assert_called_once_with(job_id)
        # Cancelled job must free the unique slot so Resume can recreate with the same logical key.
        self.assertNotEqual(job.idempotency_key, logical_key)
        self.assertTrue(
            job.idempotency_key is None or str(job.idempotency_key).endswith(f":cancelled:{job_id}"),
            job.idempotency_key,
        )

    def test_resume_after_pause_recreates_download_job(self) -> None:
        old_job = uuid4()
        new_job = uuid4()
        item = queue_item(
            job_id=old_job,
            held_at=datetime(2026, 7, 14, tzinfo=UTC),
            status=ReupQueueStatus.WAITING_FOR_MEDIA,
        )
        logical_key = f"reup-queue:{item.id}:download"
        stale_job = SimpleNamespace(id=old_job, status=JobStatus.CANCELLED, idempotency_key=logical_key)
        fake_db = FakeActionDb(item, job=stale_job)
        download_service = MagicMock()
        download_service.create_download_job.return_value = SimpleNamespace(job_id=str(new_job))

        updated = ReupQueueService(fake_db, download_service=download_service).apply_action(
            item.id,
            action=ReupQueueAction.RESUME,
        )

        self.assertIsNone(updated.held_at)
        self.assertEqual(updated.job_id, new_job)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_MEDIA)
        download_service.create_download_job.assert_called_once()
        call_kwargs = download_service.create_download_job.call_args.kwargs
        self.assertEqual(call_kwargs.get("idempotency_key"), logical_key)
        request_arg = download_service.create_download_job.call_args.args[0]
        self.assertTrue(getattr(request_arg, "force_refresh", False))
        self.assertNotEqual(stale_job.idempotency_key, logical_key)


if __name__ == "__main__":
    unittest.main()
