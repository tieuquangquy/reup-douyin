from __future__ import annotations

import unittest
from types import SimpleNamespace
from uuid import uuid4

from src.audio_pipeline.types import AudioAnalysisRequest, TranslationPreset
from src.enums import ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_queue_service import ReupQueueService


class FakeActionDb:
    def __init__(self, item):
        self.item = item
        self.committed = False
        self.refreshed = []
        self._jobs: dict = {}

    def scalar(self, _stmt):
        return self.item

    def get(self, _model, job_id):
        return self._jobs.get(job_id)

    def commit(self):
        self.committed = True

    def refresh(self, item):
        self.refreshed.append(item)


class FakeAudioAnalysisService:
    def __init__(self):
        self.calls: list[dict] = []

    def create_analysis_job(
        self,
        request: AudioAnalysisRequest,
        *,
        idempotency_key: str | None = None,
        commit: bool = True,
    ):
        self.calls.append(
            {
                "source_video_id": request.source_video_id,
                "translation_preset": request.translation_preset,
                "force_refresh": request.force_refresh,
                "skip_translation": request.skip_translation,
                "idempotency_key": idempotency_key,
            }
        )
        return SimpleNamespace(id=uuid4(), job_type="ANALYZE_AUDIO")


def queue_item(**overrides):
    item_id = uuid4()
    defaults = {
        "id": item_id,
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
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "job_id": uuid4(),
        "source_video": None,
        "video_candidate": None,
        "metadata_json": {"download_job_completed": True},
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReupQueueMarkMediaReadyAnalyzeTests(unittest.TestCase):
    def test_mark_media_ready_enqueues_analyze_audio_and_waits_for_metadata(self) -> None:
        item = queue_item()
        analysis = FakeAudioAnalysisService()
        updated = ReupQueueService(FakeActionDb(item), audio_analysis_service=analysis).apply_action(
            item.id,
            action=ReupQueueAction.MARK_MEDIA_READY,
            note="media confirmed",
        )

        self.assertEqual(len(analysis.calls), 1)
        self.assertEqual(analysis.calls[0]["source_video_id"], item.source_video_id)
        self.assertEqual(analysis.calls[0]["idempotency_key"], f"reup-queue:{item.id}:analyze-audio")
        self.assertEqual(analysis.calls[0]["translation_preset"], TranslationPreset.LITERAL_SAFE)
        self.assertTrue(analysis.calls[0]["skip_translation"])
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(updated.media_prep_status, ReupQueueMediaPrepStatus.WAITING_FOR_METADATA)
        self.assertIsNotNone(updated.media_ready_at)
        self.assertIsNotNone(updated.job_id)

    def test_mark_media_ready_reuses_existing_analyze_audio_job_id(self) -> None:
        analyze_job_id = uuid4()
        item = queue_item(job_id=analyze_job_id)
        db = FakeActionDb(item)
        db._jobs[analyze_job_id] = SimpleNamespace(id=analyze_job_id, job_type="ANALYZE_AUDIO")
        analysis = FakeAudioAnalysisService()

        updated = ReupQueueService(db, audio_analysis_service=analysis).apply_action(
            item.id,
            action=ReupQueueAction.MARK_MEDIA_READY,
        )

        self.assertEqual(analysis.calls, [])
        self.assertEqual(updated.job_id, analyze_job_id)
        self.assertEqual(updated.status, ReupQueueStatus.WAITING_FOR_METADATA)

    def test_mark_media_ready_recreates_analyze_job_when_previous_failed(self) -> None:
        from src.enums import JobStatus, JobType

        failed_id = uuid4()
        item = queue_item(
            job_id=failed_id,
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        )
        db = FakeActionDb(item)
        db._jobs[failed_id] = SimpleNamespace(
            id=failed_id,
            job_type=JobType.ANALYZE_AUDIO,
            status=JobStatus.FAILED,
            idempotency_key=f"reup-queue:{item.id}:analyze-audio",
        )
        analysis = FakeAudioAnalysisService()

        updated = ReupQueueService(db, audio_analysis_service=analysis).apply_action(
            item.id,
            action=ReupQueueAction.MARK_MEDIA_READY,
        )

        self.assertEqual(len(analysis.calls), 1)
        self.assertNotEqual(updated.job_id, failed_id)
        self.assertTrue(str(db._jobs[failed_id].idempotency_key).endswith(f":cancelled:{failed_id}"))


if __name__ == "__main__":
    unittest.main()
