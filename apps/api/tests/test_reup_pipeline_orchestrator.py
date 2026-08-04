"""Unit tests for Reup auto pipeline orchestrator transitions."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobType, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_pipeline_meta import (
    PIPELINE_MODE_AUTO_TO_RENDER,
    PIPELINE_MODE_AUTO_TO_TTS,
    PIPELINE_MODE_MANUAL,
    PIPELINE_STEP_ANALYZE_AUDIO,
    PIPELINE_STEP_OCR,
    PIPELINE_STEP_QUALITY_REVIEW,
    PIPELINE_STEP_READY_FINAL,
    PIPELINE_STEP_RENDER,
    PIPELINE_STEP_TRANSLATE,
    PIPELINE_STEP_TRANSLATION_REVIEW,
    PIPELINE_STEP_TTS,
    get_pipeline_mode,
    get_pipeline_step,
    is_auto_pipeline,
    set_pipeline_meta,
)
from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator


class FakeScalarResult:
    def __init__(self, values):
        self._values = values

    def unique(self):
        return self

    def all(self):
        return list(self._values)

    def __iter__(self):
        return iter(self._values)


class FakeDb:
    def __init__(self, items):
        self.items = items
        self.flushes = 0

    def scalars(self, _stmt):
        return FakeScalarResult(self.items)

    def flush(self):
        self.flushes += 1

    def get(self, _model, _id):
        return None


def auto_item(**overrides):
    item_id = uuid4()
    job_id = uuid4()
    defaults = {
        "id": item_id,
        "workspace_id": uuid4(),
        "video_candidate_id": uuid4(),
        "source_video_id": uuid4(),
        "status": ReupQueueStatus.WAITING_FOR_MEDIA,
        "media_prep_status": ReupQueueMediaPrepStatus.WAITING_FOR_MEDIA,
        "media_ready_at": None,
        "held_at": None,
        "failed_at": None,
        "blocked_at": None,
        "blocked_reason": None,
        "last_error_code": None,
        "last_error_message": None,
        "last_action_note": None,
        "started_at": None,
        "job_id": job_id,
        "source_video": SimpleNamespace(metadata_json={"has_speech": True}),
        "metadata_json": {
            "pipeline_mode": PIPELINE_MODE_AUTO_TO_TTS,
            "pipeline_hold": False,
            "pipeline_step": "download",
        },
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class ReupPipelineOrchestratorTests(unittest.TestCase):
    def test_auto_ocr_job_explicitly_uses_quality_workflow(self) -> None:
        item = auto_item()
        job = SimpleNamespace(id=uuid4())
        with patch(
            "src.ocr_pipeline.services.ocr_service.OcrPipelineService.create_ocr_job",
            return_value=job,
        ) as create:
            result = ReupPipelineOrchestrator(FakeDb([item]))._ensure_ocr(item)

        self.assertTrue(result)
        request = create.call_args.args[0]
        self.assertEqual(request.workflow_version, "QUALITY_LOCALIZATION_V24_1")

    def test_quality_ocr_completion_parks_at_operator_review(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_OCR,
            }
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.ANALYZE_OCR,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            payload_json={"workflow_version": "QUALITY_LOCALIZATION_V24_1"},
            error_code=None,
            error_message=None,
        )
        with patch(
            "src.services.quality_localization_service.QualityLocalizationService.summary",
            return_value={
                "workflow_stage": "WAITING_OCR_REVIEW",
                "can_render_final": False,
            },
        ), patch.object(ReupPipelineOrchestrator, "_ensure_render") as render:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)

        self.assertEqual(updated, 1)
        render.assert_not_called()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_QUALITY_REVIEW)
        self.assertEqual(item.metadata_json["quality_workflow_stage"], "WAITING_OCR_REVIEW")

    def test_quality_preview_completion_refreshes_parked_queue_stage(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_QUALITY_REVIEW,
            }
        )
        job = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.RENDER_PREVIEW,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            workspace_id=item.workspace_id,
            error_code=None,
            error_message=None,
        )
        with patch(
            "src.services.quality_localization_service.QualityLocalizationService.summary",
            return_value={
                "workflow_stage": "WAITING_RESIDUAL_TRIAGE",
                "can_render_final": False,
            },
        ), patch.object(ReupPipelineOrchestrator, "admit_waiting_items"):
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)

        self.assertEqual(updated, 1)
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_QUALITY_REVIEW)
        self.assertEqual(
            item.metadata_json["quality_workflow_stage"],
            "WAITING_RESIDUAL_TRIAGE",
        )
        self.assertIn("WAITING_RESIDUAL_TRIAGE", item.last_action_note)

    def test_external_cancel_frees_auto_lane_as_needs_attention(self) -> None:
        item = auto_item()
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.CANCELLED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))
        with patch.object(orchestrator, "admit_waiting_items"):
            updated = orchestrator.on_job_terminal(job)
        self.assertEqual(updated, 1)
        self.assertEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)
        self.assertEqual(item.last_error_code, "PIPELINE_JOB_CANCELLED")

    def test_missing_stage_job_is_recreated_before_admission_count(self) -> None:
        missing_id = uuid4()
        item = auto_item(
            job_id=None,
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_TTS,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_TTS,
                "tts_job_id": str(missing_id),
            },
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))
        with patch.object(orchestrator, "_ensure_tts", return_value=True) as ensure:
            repaired = orchestrator.reconcile_stale_auto_items([item])
        self.assertEqual(repaired, 1)
        ensure.assert_called_once_with(item)
        self.assertIn("recovered a missing tts job", str(item.last_action_note).lower())

    def test_auto_tts_job_uses_bound_recipe_runtime_authority(self) -> None:
        item = auto_item()
        authority = {
            "provider": "omnivoice",
            "model_id": "k2-fsa/OmniVoice",
            "voice_id": "instruct:vi_female_north",
            "language_code": "vi",
            "speaking_rate": 1.0,
            "runtime_config_sha256": "a" * 64,
            "authority": "e2e_render_prep_manifests_v1",
        }
        job = SimpleNamespace(id=uuid4())
        with patch(
            "src.services.pipeline_recipe_runtime.load_bound_recipe_tts",
            return_value=authority,
        ), patch(
            "src.tts_pipeline.services.tts_service.TtsPipelineService.create_tts_job",
            return_value=job,
        ) as create:
            result = ReupPipelineOrchestrator(FakeDb([item]))._ensure_tts(item)

        self.assertTrue(result)
        request = create.call_args.args[0]
        self.assertEqual(request.runtime_authority, authority)
        self.assertEqual(request.runtime_authority["voice_id"], "instruct:vi_female_north")

    def test_auto_tts_parks_for_translation_review_without_failed_state(self) -> None:
        from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode

        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        )
        with patch(
            "src.services.pipeline_recipe_runtime.load_bound_recipe_tts",
            return_value={"voice_id": "instruct:vi_female_north"},
        ), patch(
            "src.tts_pipeline.services.tts_service.TtsPipelineService.create_tts_job",
            side_effect=TtsPipelineError(
                TtsPipelineErrorCode.TRANSLATION_REVIEW_REQUIRED,
                "segment 0 requires review",
            ),
        ):
            result = ReupPipelineOrchestrator(FakeDb([item]))._ensure_tts(item)

        self.assertTrue(result)
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TRANSLATION_REVIEW)
        self.assertEqual(item.last_error_code, "translation_review_required")
        self.assertIsNone(item.job_id)

    def test_manual_mode_does_not_advance(self) -> None:
        item = auto_item(metadata_json={"pipeline_mode": PIPELINE_MODE_MANUAL})
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 0)
        self.assertFalse(is_auto_pipeline(item))

    def test_download_complete_enqueues_analyze(self) -> None:
        item = auto_item()
        analyze_id = uuid4()
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_analyze_audio", return_value=True) as ensure:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure.assert_called_once()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_ANALYZE_AUDIO)

    def test_hold_blocks_advance(self) -> None:
        item = auto_item()
        set_pipeline_meta(item, hold=True)
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_analyze_audio") as ensure:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 0)
        ensure.assert_not_called()

    def test_analyze_complete_enqueues_translate(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_TTS,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_ANALYZE_AUDIO,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.ANALYZE_AUDIO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_translation", return_value=True) as ensure:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure.assert_called_once()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TRANSLATE)

    def test_analyze_no_dialogue_stops_at_ready_final(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            source_video=SimpleNamespace(metadata_json={"has_speech": False, "dialogue_phase": "no_dialogue"}),
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_TTS,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_ANALYZE_AUDIO,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.ANALYZE_AUDIO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_translation") as ensure:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure.assert_not_called()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_READY_FINAL)

    def test_analyze_no_dialogue_still_renders_for_auto_to_render(self) -> None:
        """No speech does not mean no burned-in Chinese text: OCR + render must still run."""
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            source_video=SimpleNamespace(metadata_json={"has_speech": False, "dialogue_phase": "no_dialogue"}),
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_ANALYZE_AUDIO,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.ANALYZE_AUDIO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with (
            patch.object(ReupPipelineOrchestrator, "_ensure_translation") as ensure_translate,
            patch.object(ReupPipelineOrchestrator, "_ensure_ocr", return_value=True) as ensure_ocr,
        ):
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure_translate.assert_not_called()
        ensure_ocr.assert_called_once()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_OCR)
        self.assertNotEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)

    def test_ocr_complete_renders_silent_clip(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            source_video=SimpleNamespace(metadata_json={"has_speech": False, "dialogue_phase": "no_dialogue"}),
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_OCR,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.ANALYZE_OCR,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_render", return_value=True) as ensure_render:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure_render.assert_called_once()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_RENDER)

    def test_tts_complete_stops_for_auto_to_tts(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_TTS,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_TTS,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.SYNTHESIZE_TTS,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_ocr") as ensure_ocr:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure_ocr.assert_not_called()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_READY_FINAL)
        self.assertEqual(get_pipeline_mode(item), PIPELINE_MODE_AUTO_TO_TTS)

    def test_tts_complete_enqueues_ocr_for_auto_to_render(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_TTS,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.SYNTHESIZE_TTS,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        with patch.object(ReupPipelineOrchestrator, "_ensure_ocr", return_value=True) as ensure_ocr:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        ensure_ocr.assert_called_once()

    def test_failed_job_marks_needs_attention(self) -> None:
        item = auto_item()
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.FAILED,
            source_video_id=item.source_video_id,
            error_code="DOWNLOAD_FAILED",
            error_message="boom",
        )
        updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)
        self.assertEqual(updated, 1)
        self.assertEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)
        self.assertEqual(item.last_error_code, "DOWNLOAD_FAILED")


if __name__ == "__main__":
    unittest.main()
