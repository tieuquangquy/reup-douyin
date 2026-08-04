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
        "metadata_json": {},
        "source_video": None,
        "video_candidate": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class PauseDuringProgressTests(unittest.TestCase):
    def test_waiting_for_media_offers_hold_while_download_running(self) -> None:
        job_id = uuid4()
        item = queue_item(
            held_at=None,
            job_id=job_id,
            job=SimpleNamespace(id=job_id, job_type="DOWNLOAD_VIDEO", status=JobStatus.RUNNING),
        )
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.HOLD, actions)
        self.assertNotIn(ReupQueueAction.RESUME, actions)

    def test_waiting_for_media_offers_resume_when_download_idle(self) -> None:
        """Stuck/cancelled download must expose Resume/restart without Pause first."""
        job_id = uuid4()
        item = queue_item(
            held_at=None,
            job_id=job_id,
            job=SimpleNamespace(id=job_id, job_type="DOWNLOAD_VIDEO", status=JobStatus.CANCELLED),
        )
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.RESUME, actions)
        self.assertNotIn(ReupQueueAction.HOLD, actions)

    def test_waiting_for_media_offers_resume_when_no_job(self) -> None:
        item = queue_item(held_at=None, job_id=None, job=None)
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.RESUME, actions)
        self.assertNotIn(ReupQueueAction.HOLD, actions)

    def test_waiting_for_media_offers_resume_when_paused(self) -> None:
        item = queue_item(held_at=datetime(2026, 7, 14, tzinfo=UTC))
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.RESUME, actions)
        self.assertNotIn(ReupQueueAction.HOLD, actions)

    def test_waiting_for_metadata_offers_retry_when_analyze_failed(self) -> None:
        job_id = uuid4()
        item = queue_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
            job_id=job_id,
            job=SimpleNamespace(id=job_id, job_type="ANALYZE_AUDIO", status=JobStatus.FAILED),
        )
        actions = available_action_values(item)
        self.assertIn(ReupQueueAction.RETRY, actions)
        self.assertIn(ReupQueueAction.MARK_MEDIA_READY, actions)

    def test_waiting_for_metadata_hides_retry_when_analyze_still_running(self) -> None:
        job_id = uuid4()
        item = queue_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
            job_id=job_id,
            job=SimpleNamespace(id=job_id, job_type="ANALYZE_AUDIO", status=JobStatus.RUNNING),
        )
        actions = available_action_values(item)
        self.assertNotIn(ReupQueueAction.RETRY, actions)

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

    def test_auto_pipeline_resume_after_pause_recreates_download_job(self) -> None:
        """Pause cancels DOWNLOAD; auto Resume must not reuse the cancelled job_id."""
        old_job = uuid4()
        new_job = uuid4()
        item = queue_item(
            job_id=old_job,
            held_at=datetime(2026, 7, 14, tzinfo=UTC),
            status=ReupQueueStatus.WAITING_FOR_MEDIA,
            metadata_json={
                "pipeline_mode": "auto_to_tts",
                "pipeline_hold": True,
                "pipeline_step": "download",
            },
        )
        logical_key = f"reup-queue:{item.id}:download"
        stale_job = SimpleNamespace(
            id=old_job,
            status=JobStatus.CANCELLED,
            idempotency_key=f"{logical_key}:cancelled:{old_job}",
            job_type="DOWNLOAD_VIDEO",
        )
        fake_db = FakeActionDb(item, job=stale_job)
        download_service = MagicMock()
        download_service.create_download_job.return_value = SimpleNamespace(job_id=str(new_job))

        with patch.object(ReupQueueService, "_get_download_service", return_value=download_service):
            updated = ReupQueueService(fake_db, download_service=download_service).apply_action(
                item.id,
                action=ReupQueueAction.RESUME,
            )

        self.assertIsNone(updated.held_at)
        self.assertEqual(updated.metadata_json.get("pipeline_hold"), False)
        self.assertEqual(updated.job_id, new_job)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_MEDIA)
        download_service.create_download_job.assert_called_once()
        self.assertEqual(
            download_service.create_download_job.call_args.kwargs.get("idempotency_key"),
            logical_key,
        )

    def test_hold_during_metadata_keeps_transcript_stage(self) -> None:
        job_id = uuid4()
        item = queue_item(
            job_id=job_id,
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
            media_ready_at=datetime(2026, 7, 14, tzinfo=UTC),
        )
        fake_db = FakeActionDb(item)
        cancel = MagicMock(return_value=SimpleNamespace(id=job_id, status=JobStatus.CANCELLED))

        with patch("src.services.job_service.JobService") as job_service_cls:
            job_service_cls.return_value.cancel_job = cancel
            updated = ReupQueueService(fake_db).apply_action(
                item.id,
                action=ReupQueueAction.HOLD,
                note="Operator paused transcript",
            )

        cancel.assert_called_once_with(job_id)
        self.assertIsNotNone(updated.held_at)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.media_prep_status, ReupQueueMediaPrepStatus.WAITING_FOR_METADATA)
        self.assertIsNotNone(updated.media_ready_at)

    def test_mark_media_ready_clears_held_at(self) -> None:
        analyze_job = uuid4()
        item = queue_item(
            held_at=datetime(2026, 7, 14, tzinfo=UTC),
            status=ReupQueueStatus.WAITING_FOR_MEDIA,
            job_id=None,
        )
        fake_db = FakeActionDb(item)
        audio_service = MagicMock()
        audio_service.create_analysis_job.return_value = SimpleNamespace(id=analyze_job)

        updated = ReupQueueService(fake_db, audio_analysis_service=audio_service).apply_action(
            item.id,
            action=ReupQueueAction.MARK_MEDIA_READY,
            media_prep_notes="Operator confirmed media; enqueue audio analysis.",
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        )

        self.assertIsNone(updated.held_at)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.job_id, analyze_job)

    def test_resume_during_metadata_restarts_analyze_not_download(self) -> None:
        old_job = uuid4()
        new_job = uuid4()
        item = queue_item(
            job_id=old_job,
            held_at=datetime(2026, 7, 14, tzinfo=UTC),
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
            media_ready_at=datetime(2026, 7, 14, tzinfo=UTC),
            metadata_json={"analyze_audio_job_id": str(old_job)},
        )
        logical_key = f"reup-queue:{item.id}:analyze-audio"
        stale_job = SimpleNamespace(id=old_job, status=JobStatus.CANCELLED, idempotency_key=logical_key)
        fake_db = FakeActionDb(item, job=stale_job)
        audio_service = MagicMock()
        audio_service.create_analysis_job.return_value = SimpleNamespace(id=new_job)
        download_service = MagicMock()

        updated = ReupQueueService(
            fake_db,
            download_service=download_service,
            audio_analysis_service=audio_service,
        ).apply_action(item.id, action=ReupQueueAction.RESUME)

        self.assertIsNone(updated.held_at)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.media_prep_status, ReupQueueMediaPrepStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.job_id, new_job)
        audio_service.create_analysis_job.assert_called_once()
        download_service.create_download_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
