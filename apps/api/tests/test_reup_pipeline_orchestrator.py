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
    PIPELINE_ERROR_KEY,
    PIPELINE_FAILED_STEP_KEY,
    PIPELINE_STEP_ANALYZE_AUDIO,
    PIPELINE_STEP_NEEDS_ATTENTION,
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
        self.scalar_value = None

    def scalars(self, _stmt):
        return FakeScalarResult(self.items)

    def flush(self):
        self.flushes += 1

    def get(self, _model, _id):
        return None

    def scalar(self, _stmt):
        return self.scalar_value


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
    def test_ensure_step_catches_up_a_job_that_is_already_completed(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_ANALYZE_AUDIO,
            }
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.ANALYZE_AUDIO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            payload_json={},
            error_code=None,
            error_message=None,
        )
        db = FakeDb([item])
        db.get = lambda _model, entity_id: job if entity_id == job.id else None
        orchestrator = ReupPipelineOrchestrator(db)

        with patch(
            "src.services.pipeline_recipe_runtime.ensure_item_recipe_binding"
        ), patch.object(
            orchestrator, "_ensure_analyze_audio", return_value=True
        ), patch.object(
            orchestrator, "_ensure_translation", return_value=True
        ) as translate:
            orchestrator._ensure_step(PIPELINE_STEP_ANALYZE_AUDIO, item)

        translate.assert_called_once_with(item)
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TRANSLATE)
        self.assertEqual(
            item.metadata_json.get("pipeline_last_completed_step"),
            PIPELINE_STEP_ANALYZE_AUDIO,
        )

    def test_delayed_old_completion_cannot_rewind_or_skip_current_stage(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_TRANSLATE,
                "pipeline_last_completed_step": PIPELINE_STEP_ANALYZE_AUDIO,
            }
        )
        job = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.DOWNLOAD_VIDEO,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            workspace_id=item.workspace_id,
            payload_json={},
            error_code=None,
            error_message=None,
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))

        with patch.object(orchestrator, "_find_items_for_job", return_value=[item]), patch.object(
            orchestrator, "_ensure_analyze_audio"
        ) as analyze, patch.object(orchestrator, "admit_waiting_items"):
            updated = orchestrator.on_job_terminal(job)

        self.assertEqual(updated, 0)
        analyze.assert_not_called()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TRANSLATE)
        self.assertEqual(
            item.metadata_json.get("pipeline_last_completed_step"),
            PIPELINE_STEP_ANALYZE_AUDIO,
        )

    def test_auto_render_pass_finalizes_local_handoff_boundary(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_RENDER,
            }
        )
        render = SimpleNamespace(id=uuid4(), source_video_id=item.source_video_id, version=1)
        db = FakeDb([item])
        db.scalar_value = render
        job = SimpleNamespace(
            id=uuid4(),
            payload_json={"workflow_version": "QUALITY_LOCALIZATION_V24_1"},
        )
        orchestrator = ReupPipelineOrchestrator(db)
        verdict = SimpleNamespace(status="pass", can_auto_finish=True, summary="pass", to_dict=lambda: {"status": "pass"})
        with patch.object(orchestrator, "_render_qa_verdict", return_value=verdict), patch(
            "src.render_pipeline.services.render_service.RenderService"
        ) as render_service:
            assert orchestrator._auto_finalize_quality_render(item, job)
            render_service.return_value.mark_publish_ready.assert_called_once_with(render.id)

        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_READY_FINAL)
        self.assertEqual(item.render_output_id, render.id)
        self.assertTrue(item.metadata_json["quality_auto_finalized"])

    def test_auto_ocr_job_explicitly_uses_quality_workflow(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_OCR,
            }
        )
        job = SimpleNamespace(id=uuid4())
        with patch(
            "src.ocr_pipeline.services.ocr_service.OcrPipelineService.create_ocr_job",
            return_value=job,
        ) as create:
            result = ReupPipelineOrchestrator(FakeDb([item]))._ensure_ocr(item)

        self.assertTrue(result)
        request = create.call_args.args[0]
        self.assertEqual(request.workflow_version, "QUALITY_LOCALIZATION_V24_1")
        self.assertTrue(request.auto_advance)

    def test_quality_ocr_completion_enqueues_deterministic_auto_review(self) -> None:
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
                "review_objects": [
                    {
                        "content_id": "ocr_1",
                        "ocr_text_candidate": "字幕",
                        "provenance_classifications": ["EDITOR_OVERLAY"],
                    }
                ],
            },
        ), patch.object(
            ReupPipelineOrchestrator, "_ensure_auto_ocr_review", return_value=True
        ) as auto_review, patch.object(
            ReupPipelineOrchestrator, "_ensure_render"
        ) as render:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)

        self.assertEqual(updated, 1)
        render.assert_not_called()
        auto_review.assert_called_once()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_OCR)

    def test_quality_ocr_resume_reuses_approved_audio_and_enqueues_visual_preview(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_OCR,
                "pipeline_last_completed_step": PIPELINE_STEP_OCR,
                "tts_job_id": str(uuid4()),
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
        summary = {
            "workflow_stage": "AUDIO_APPROVED",
            "can_render_final": False,
            "audio_review_status": "AUDIO_APPROVED",
            "translation_objects": [
                {"content_id": "ocr_1", "vi_text_candidate": "Bản dịch đã khóa"}
            ],
        }
        with patch(
            "src.services.quality_localization_service.QualityLocalizationService.summary",
            return_value=summary,
        ), patch.object(
            ReupPipelineOrchestrator, "_ensure_quality_preview", return_value=True
        ) as preview, patch.object(
            ReupPipelineOrchestrator, "_ensure_tts"
        ) as tts:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)

        self.assertEqual(updated, 1)
        preview.assert_called_once_with(item, summary=summary)
        tts.assert_not_called()

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
        ), patch.object(ReupPipelineOrchestrator, "admit_waiting_items"), patch.object(
            ReupPipelineOrchestrator, "_ensure_auto_residual_remediation", return_value=True
        ) as auto_residual:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)

        self.assertEqual(updated, 1)
        auto_residual.assert_called_once_with(item)

    def test_failed_preview_output_qa_enqueues_encoded_residual_remediation(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_QUALITY_REVIEW,
            }
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.RENDER_PREVIEW,
            status=JobStatus.FAILED,
            source_video_id=item.source_video_id,
            workspace_id=item.workspace_id,
            error_code="QUALITY_OUTPUT_QA_FAILED",
            error_message="Encoded output QA failed: residual_cjk",
        )
        with patch(
            "src.services.quality_localization_service.QualityLocalizationService.summary",
            return_value={
                "workflow_stage": "WAITING_RESIDUAL_TRIAGE",
                "encoded_output_qa_current": True,
                "residual_authority_source": "encoded_visual_preview_output_qa",
            },
        ), patch.object(ReupPipelineOrchestrator, "admit_waiting_items"), patch.object(
            ReupPipelineOrchestrator, "_ensure_auto_residual_remediation", return_value=True
        ) as auto_residual:
            updated = ReupPipelineOrchestrator(FakeDb([item])).on_job_terminal(job)

        self.assertEqual(updated, 1)
        auto_residual.assert_called_once_with(item)
        self.assertNotEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)

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

    def test_auto_tts_job_delegates_active_setup_binding_to_tts_service(self) -> None:
        item = auto_item()
        job = SimpleNamespace(id=uuid4())
        with patch(
            "src.tts_pipeline.services.tts_service.TtsPipelineService.create_tts_job",
            return_value=job,
        ) as create:
            result = ReupPipelineOrchestrator(FakeDb([item]))._ensure_tts(item)

        self.assertTrue(result)
        request = create.call_args.args[0]
        self.assertIsNone(request.runtime_authority)

    def test_auto_tts_parks_for_translation_review_without_failed_state(self) -> None:
        from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode

        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        )
        with patch(
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
        self.assertEqual(item.metadata_json[PIPELINE_FAILED_STEP_KEY], "download")
        self.assertEqual(item.metadata_json[PIPELINE_ERROR_KEY]["error_domain"], "download")

    def test_translation_provider_failure_preserves_stage_and_resumes_translation_only(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.WAITING_FOR_METADATA,
            media_ready_at=object(),
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": PIPELINE_STEP_TRANSLATE,
                "pipeline_last_completed_step": PIPELINE_STEP_ANALYZE_AUDIO,
                "download_job_completed": True,
            },
        )
        job = SimpleNamespace(
            id=item.job_id,
            job_type=JobType.BUILD_TRANSLATION_DRAFT,
            status=JobStatus.FAILED,
            source_video_id=item.source_video_id,
            error_code="translation_failed",
            error_message=(
                "translation_provider_auth_failed:"
                "openai_compatible_http_403:error code: 1010"
            ),
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))

        updated = orchestrator.on_job_terminal(job)

        self.assertEqual(updated, 1)
        self.assertEqual(item.metadata_json[PIPELINE_FAILED_STEP_KEY], PIPELINE_STEP_TRANSLATE)
        context = item.metadata_json[PIPELINE_ERROR_KEY]
        self.assertEqual(context["error_domain"], "translation_provider")
        self.assertEqual(context["http_status"], 403)
        self.assertEqual(context["provider_error_code"], "1010")
        self.assertFalse(context["retryable"])
        self.assertEqual(context["recovery_action"], "CHECK_TRANSLATION_AI_CONNECTION")

        with patch.object(orchestrator, "_ensure_translation", return_value=True) as translate, patch.object(
            orchestrator, "_ensure_analyze_audio"
        ) as analyze:
            orchestrator.resume_item(item)

        translate.assert_called_once_with(item)
        analyze.assert_not_called()
        self.assertNotIn(PIPELINE_FAILED_STEP_KEY, item.metadata_json)
        self.assertNotIn(PIPELINE_ERROR_KEY, item.metadata_json)

    def test_resume_needs_attention_requeues_last_completed_ocr_only(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.FAILED_NEEDS_ATTENTION,
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": True,
                "pipeline_step": PIPELINE_STEP_NEEDS_ATTENTION,
                "pipeline_last_completed_step": PIPELINE_STEP_OCR,
            },
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))

        with patch.object(orchestrator, "_ensure_ocr", return_value=True) as ensure_ocr:
            orchestrator.resume_item(item)

        ensure_ocr.assert_called_once_with(item)
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_OCR)
        self.assertFalse(item.metadata_json["pipeline_hold"])

    def test_resume_after_operator_approved_uncertain_dialogue_continues_to_translation(self) -> None:
        item = auto_item(
            status=ReupQueueStatus.FAILED_NEEDS_ATTENTION,
            source_video=SimpleNamespace(
                metadata_json={"has_speech": True, "dialogue_phase": "source_approved"}
            ),
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": True,
                "pipeline_step": PIPELINE_STEP_NEEDS_ATTENTION,
                "pipeline_last_completed_step": PIPELINE_STEP_ANALYZE_AUDIO,
            },
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))

        with patch.object(orchestrator, "_ensure_translation", return_value=True) as translate, patch.object(
            orchestrator, "_ensure_analyze_audio"
        ) as analyze:
            orchestrator.resume_item(item)

        translate.assert_called_once_with(item)
        analyze.assert_not_called()
        self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TRANSLATE)

    def test_full_quality_frontend_chain_reaches_final_review(self) -> None:
        item = auto_item(
            metadata_json={
                "pipeline_mode": PIPELINE_MODE_AUTO_TO_RENDER,
                "pipeline_hold": False,
                "pipeline_step": "download",
            }
        )
        orchestrator = ReupPipelineOrchestrator(FakeDb([item]))

        def completed(job_type, *, payload=None):  # noqa: ANN001
            return SimpleNamespace(
                id=item.job_id,
                job_type=job_type,
                status=JobStatus.COMPLETED,
                source_video_id=item.source_video_id,
                workspace_id=item.workspace_id,
                payload_json=payload or {},
                error_code=None,
                error_message=None,
            )

        with patch.object(orchestrator, "_find_items_for_job", return_value=[item]), patch.object(
            orchestrator, "admit_waiting_items"
        ), patch.object(orchestrator, "_ensure_analyze_audio", return_value=True), patch.object(
            orchestrator, "_ensure_translation", return_value=True
        ), patch.object(orchestrator, "_ensure_tts", return_value=True), patch.object(
            orchestrator, "_ensure_ocr", return_value=True
        ), patch.object(orchestrator, "_ensure_render", return_value=True) as ensure_render, patch.object(
            orchestrator, "_render_qa_verdict", return_value=None
        ), patch.object(
            orchestrator,
            "_ensure_quality_preview",
            side_effect=lambda target, summary: bool(
                set_pipeline_meta(target, step=PIPELINE_STEP_QUALITY_REVIEW)
            ),
        ), patch(
            "src.services.quality_localization_service.QualityLocalizationService.summary",
            side_effect=[
                {
                    "workflow_stage": "WAITING_TRANSLATION_REVIEW",
                    "can_render_final": False,
                    "translation_objects": [
                        {"content_id": "c1", "vi_text_candidate": "Xin chao"}
                    ],
                },
                {"workflow_stage": "AUDIO_APPROVED", "can_render_final": True},
            ],
        ):
            orchestrator.on_job_terminal(completed(JobType.DOWNLOAD_VIDEO))
            self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_ANALYZE_AUDIO)
            orchestrator.on_job_terminal(completed(JobType.ANALYZE_AUDIO))
            self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TRANSLATE)
            orchestrator.on_job_terminal(completed(JobType.BUILD_TRANSLATION_DRAFT))
            self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_TTS)
            orchestrator.on_job_terminal(completed(JobType.SYNTHESIZE_TTS))
            self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_OCR)
            orchestrator.on_job_terminal(
                completed(
                    JobType.ANALYZE_OCR,
                    payload={"workflow_version": "QUALITY_LOCALIZATION_V24_1"},
                )
            )
            orchestrator.on_job_terminal(
                completed(JobType.RENDER_PREVIEW)
            )
            self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_RENDER)
            ensure_render.assert_called()

            orchestrator.on_job_terminal(completed(JobType.RENDER_FINAL))
            self.assertEqual(get_pipeline_step(item), PIPELINE_STEP_READY_FINAL)


if __name__ == "__main__":
    unittest.main()
