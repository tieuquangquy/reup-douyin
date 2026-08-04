"""Automation level must be switchable mid-flight, both directions.

An operator who started a clip by hand should be able to hand the rest to the pipeline,
and an auto clip should be able to be taken over without losing its place.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, ReupQueueAction, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator
from src.services.reup_queue_service import ReupQueueError, ReupQueueService, available_action_values


class FakeActionDb:
    def __init__(self, item, job=None):
        self.item = item
        self.job = job

    def scalar(self, _stmt):
        return self.item

    def get(self, _model, entity_id):
        if self.job is not None and self.job.id == entity_id:
            return self.job
        return None

    def commit(self):
        pass

    def refresh(self, _item):
        pass

    def flush(self):
        pass


def queue_item(**overrides):
    defaults = {
        "id": uuid4(),
        "workspace_id": uuid4(),
        "video_candidate_id": uuid4(),
        "source_video_id": uuid4(),
        "status": ReupQueueStatus.WAITING_FOR_METADATA,
        "media_prep_status": ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        "media_prep_notes": None,
        "media_ready_at": datetime(2026, 7, 20, tzinfo=UTC),
        "blocked_reason": None,
        "blocked_at": None,
        "held_at": None,
        "failed_at": None,
        "last_action": None,
        "last_action_at": None,
        "last_action_note": None,
        "last_error_code": None,
        "last_error_message": None,
        "started_at": datetime(2026, 7, 20, tzinfo=UTC),
        "completed_at": None,
        "cancelled_at": None,
        "job_id": None,
        "metadata_json": {},
        "source_video": SimpleNamespace(metadata_json={"has_speech": True}),
        "video_candidate": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class SetAutomationAvailabilityTests(unittest.TestCase):
    def test_offered_while_work_is_in_flight(self) -> None:
        for status, prep in (
            (ReupQueueStatus.READY_FOR_PROCESSING, ReupQueueMediaPrepStatus.NOT_STARTED),
            (ReupQueueStatus.WAITING_FOR_MEDIA, ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA),
            (ReupQueueStatus.WAITING_FOR_METADATA, ReupQueueMediaPrepStatus.WAITING_FOR_METADATA),
            (ReupQueueStatus.PROCESSING, ReupQueueMediaPrepStatus.WAITING_FOR_METADATA),
        ):
            item = queue_item(status=status, media_prep_status=prep)
            self.assertIn(
                ReupQueueAction.SET_AUTOMATION,
                available_action_values(item),
                f"{status} must allow switching automation",
            )

    def test_not_offered_on_terminal_items(self) -> None:
        for status in (ReupQueueStatus.COMPLETED, ReupQueueStatus.CANCELLED):
            item = queue_item(status=status, media_prep_status=ReupQueueMediaPrepStatus.NOT_STARTED)
            self.assertNotIn(ReupQueueAction.SET_AUTOMATION, available_action_values(item))


class SetAutomationApplyTests(unittest.TestCase):
    def test_switch_to_manual_keeps_place_and_starts_nothing(self) -> None:
        item = queue_item(
            metadata_json={
                "pipeline_mode": "auto_to_render",
                "pipeline_hold": False,
                "pipeline_step": "translate",
            }
        )
        db = FakeActionDb(item)

        with patch.object(ReupPipelineOrchestrator, "_ensure_translation") as ensure:
            updated = ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="manual"
            )

        ensure.assert_not_called()
        self.assertEqual(updated.metadata_json.get("pipeline_mode"), "manual")
        self.assertEqual(updated.metadata_json.get("pipeline_step"), "translate")

    def test_switch_to_auto_while_job_runs_only_records_intent(self) -> None:
        """The running step finishes first; the orchestrator picks up the new stop point."""
        job_id = uuid4()
        item = queue_item(
            job_id=job_id,
            metadata_json={
                "pipeline_mode": "auto_to_tts",
                "pipeline_hold": False,
                "pipeline_step": "tts",
            },
        )
        db = FakeActionDb(item, job=SimpleNamespace(id=job_id, job_type="SYNTHESIZE_TTS", status=JobStatus.RUNNING))

        with patch.object(ReupPipelineOrchestrator, "_ensure_ocr") as ensure_ocr:
            updated = ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="auto_to_render"
            )

        ensure_ocr.assert_not_called()
        self.assertEqual(updated.metadata_json.get("pipeline_mode"), "auto_to_render")
        self.assertEqual(updated.job_id, job_id)

    def test_extending_a_finished_auto_item_resumes_at_next_step(self) -> None:
        item = queue_item(
            metadata_json={
                "pipeline_mode": "auto_to_tts",
                "pipeline_hold": False,
                "pipeline_step": "ready_final",
                "pipeline_last_completed_step": "tts",
            }
        )
        db = FakeActionDb(item)

        with patch.object(ReupPipelineOrchestrator, "_ensure_ocr", return_value=True) as ensure_ocr:
            updated = ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="auto_to_render"
            )

        ensure_ocr.assert_called_once()
        self.assertEqual(updated.metadata_json.get("pipeline_step"), "ocr")

    def test_manual_item_handed_to_auto_continues_from_recorded_progress(self) -> None:
        item = queue_item(
            metadata_json={
                "pipeline_mode": "manual",
                "pipeline_step": "analyze_audio",
                "pipeline_last_completed_step": "analyze_audio",
            }
        )
        db = FakeActionDb(item)

        with patch.object(ReupPipelineOrchestrator, "_ensure_translation", return_value=True) as ensure:
            updated = ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="auto_to_render"
            )

        ensure.assert_called_once()
        self.assertEqual(updated.metadata_json.get("pipeline_mode"), "auto_to_render")
        self.assertEqual(updated.metadata_json.get("pipeline_step"), "translate")

    def test_switch_to_auto_clears_pause(self) -> None:
        item = queue_item(
            held_at=datetime(2026, 7, 20, tzinfo=UTC),
            metadata_json={
                "pipeline_mode": "manual",
                "pipeline_hold": True,
                "pipeline_step": "analyze_audio",
                "pipeline_last_completed_step": "analyze_audio",
            },
        )
        db = FakeActionDb(item)

        with patch.object(ReupPipelineOrchestrator, "_ensure_translation", return_value=True):
            updated = ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="auto_to_render"
            )

        self.assertIsNone(updated.held_at)
        self.assertIs(updated.metadata_json.get("pipeline_hold"), False)

    def test_silent_clip_handed_to_auto_skips_to_ocr(self) -> None:
        item = queue_item(
            source_video=SimpleNamespace(metadata_json={"has_speech": False, "dialogue_phase": "no_dialogue"}),
            metadata_json={
                "pipeline_mode": "manual",
                "pipeline_step": "analyze_audio",
                "pipeline_last_completed_step": "analyze_audio",
            },
        )
        db = FakeActionDb(item)

        with patch.object(ReupPipelineOrchestrator, "_ensure_ocr", return_value=True) as ensure_ocr:
            updated = ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="auto_to_render"
            )

        ensure_ocr.assert_called_once()
        self.assertEqual(updated.metadata_json.get("pipeline_step"), "ocr")

    def test_unknown_mode_is_rejected(self) -> None:
        item = queue_item(metadata_json={"pipeline_mode": "manual"})
        db = FakeActionDb(item)

        with self.assertRaises(ReupQueueError) as ctx:
            ReupQueueService(db).apply_action(
                item.id, action=ReupQueueAction.SET_AUTOMATION, pipeline_mode="auto_to_publish"
            )
        self.assertEqual(ctx.exception.code, "INVALID_PIPELINE_MODE")

    def test_missing_mode_is_rejected(self) -> None:
        item = queue_item(metadata_json={"pipeline_mode": "manual"})
        db = FakeActionDb(item)

        with self.assertRaises(ReupQueueError):
            ReupQueueService(db).apply_action(item.id, action=ReupQueueAction.SET_AUTOMATION)


class ProgressRecordingTests(unittest.TestCase):
    """Manual items must also record progress, otherwise handing them to auto guesses."""

    def test_completed_job_records_step_for_manual_item(self) -> None:
        item = queue_item(metadata_json={"pipeline_mode": "manual", "pipeline_step": "analyze_audio"})
        job = SimpleNamespace(
            id=uuid4(),
            job_type="ANALYZE_AUDIO",
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        item.job_id = job.id

        class Scalars:
            def __init__(self, values):
                self._values = values

            def unique(self):
                return self

            def __iter__(self):
                return iter(self._values)

        db = MagicMock()
        db.scalars.return_value = Scalars([item])

        ReupPipelineOrchestrator(db).on_job_terminal(job)

        self.assertEqual(item.metadata_json.get("pipeline_last_completed_step"), "analyze_audio")
        self.assertEqual(item.metadata_json.get("pipeline_mode"), "manual")


if __name__ == "__main__":
    unittest.main()
