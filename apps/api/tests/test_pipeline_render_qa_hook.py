"""A finished render must be graded before the item is called ready."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobType, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator
from src.services.render_qa_gate import (
    RenderQaCheck,
    RenderQaCheckStatus,
    RenderQaStatus,
    RenderQaVerdict,
)


def _render_job(item: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        job_type=JobType.RENDER_FINAL,
        status=JobStatus.COMPLETED,
        source_video_id=item.source_video_id,
        error_code=None,
        error_message=None,
    )


def _item() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        source_video_id=uuid4(),
        source_video=SimpleNamespace(metadata_json={"dialogue_phase": "has_dialogue"}),
        status=ReupQueueStatus.WAITING_FOR_METADATA,
        media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        metadata_json={"pipeline_mode": "auto_to_render", "pipeline_step": "render"},
        job_id=None,
        last_action_note=None,
        last_error_code=None,
        last_error_message=None,
        blocked_reason=None,
        blocked_at=None,
        failed_at=None,
    )


def _verdict(status: RenderQaStatus, key: str = "duration_match") -> RenderQaVerdict:
    check_status = {
        RenderQaStatus.PASS: RenderQaCheckStatus.PASS,
        RenderQaStatus.WARN: RenderQaCheckStatus.WARN,
        RenderQaStatus.FAIL: RenderQaCheckStatus.FAIL,
    }[status]
    return RenderQaVerdict(
        status=status,
        checks=[RenderQaCheck(key, check_status, "detail")],
        summary=f"summary {status}",
    )


class RenderQaHookTests(unittest.TestCase):
    def test_failed_qa_stops_for_operator(self) -> None:
        item = _item()
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        with patch.object(
            ReupPipelineOrchestrator, "_render_qa_verdict", return_value=_verdict(RenderQaStatus.FAIL)
        ):
            handled = orchestrator._advance_after_success(item, _render_job(item))

        self.assertTrue(handled)
        self.assertEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)
        self.assertEqual(item.last_error_code, "RENDER_QA_FAILED")
        self.assertEqual(item.metadata_json["render_qa"]["status"], "fail")

    def test_passing_qa_finishes_and_records_verdict(self) -> None:
        item = _item()
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        with patch.object(
            ReupPipelineOrchestrator, "_render_qa_verdict", return_value=_verdict(RenderQaStatus.PASS)
        ):
            handled = orchestrator._advance_after_success(item, _render_job(item))

        self.assertTrue(handled)
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(item.metadata_json["pipeline_step"], "ready_final")
        self.assertEqual(item.metadata_json["render_qa"]["status"], "pass")

    def test_warning_qa_still_reaches_review_but_is_flagged(self) -> None:
        item = _item()
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        with patch.object(
            ReupPipelineOrchestrator, "_render_qa_verdict", return_value=_verdict(RenderQaStatus.WARN)
        ):
            handled = orchestrator._advance_after_success(item, _render_job(item))

        self.assertTrue(handled)
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(item.metadata_json["render_qa"]["status"], "warn")
        self.assertIn("QA", item.last_action_note or "")

    def test_qa_crash_does_not_block_the_pipeline(self) -> None:
        item = _item()
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        with patch(
            "src.services.render_qa_gate.collect_render_qa_metrics",
            side_effect=RuntimeError("scanner exploded"),
        ):
            handled = orchestrator._advance_after_success(item, _render_job(item))

        self.assertTrue(handled)
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(item.metadata_json["pipeline_step"], "ready_final")

    def test_qa_runs_only_after_render(self) -> None:
        item = _item()
        item.metadata_json = {"pipeline_mode": "auto_to_render", "pipeline_step": "ocr"}
        ocr_job = SimpleNamespace(
            id=uuid4(),
            job_type=JobType.ANALYZE_OCR,
            status=JobStatus.COMPLETED,
            source_video_id=item.source_video_id,
            error_code=None,
            error_message=None,
        )
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        with (
            patch.object(ReupPipelineOrchestrator, "_ensure_render", return_value=True),
            patch.object(ReupPipelineOrchestrator, "_render_qa_verdict") as qa,
        ):
            orchestrator._advance_after_success(item, ocr_job)

        qa.assert_not_called()


if __name__ == "__main__":
    unittest.main()
