"""Auto pipeline must stop for review when dialogue detection is uncertain.

Silently treating "ASR heard nothing" as "no dialogue" ships a video without the
Vietnamese voice-over it needed, and nobody finds out until publish.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from src.enums import JobStatus, JobType, ReupQueueMediaPrepStatus, ReupQueueStatus
from src.services.reup_pipeline_orchestrator import ReupPipelineOrchestrator


def _analyze_job(item: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        job_type=JobType.ANALYZE_AUDIO,
        status=JobStatus.COMPLETED,
        source_video_id=item.source_video_id,
        error_code=None,
        error_message=None,
    )


def _item(meta: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        source_video_id=uuid4(),
        source_video=SimpleNamespace(metadata_json=meta),
        status=ReupQueueStatus.WAITING_FOR_METADATA,
        media_prep_status=ReupQueueMediaPrepStatus.WAITING_FOR_METADATA,
        metadata_json={"pipeline_mode": "auto_to_tts", "pipeline_step": "analyze_audio"},
        job_id=None,
        last_action_note=None,
        last_error_code=None,
        last_error_message=None,
        blocked_reason=None,
        blocked_at=None,
        failed_at=None,
    )


class DialogueUncertainRoutingTests(unittest.TestCase):
    def test_uncertain_dialogue_stops_for_operator(self) -> None:
        item = _item({"dialogue_phase": "dialogue_uncertain", "has_speech": True, "transcript_count": 0})
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        handled = orchestrator._advance_after_success(item, _analyze_job(item))

        self.assertTrue(handled)
        self.assertEqual(item.status, ReupQueueStatus.FAILED_NEEDS_ATTENTION)
        self.assertEqual(item.last_error_code, "DIALOGUE_DETECTION_UNCERTAIN")
        self.assertIn("dialogue", (item.last_error_message or "").lower())
        self.assertFalse(orchestrator._should_skip_dubbing(item))

    def test_measured_no_dialogue_still_skips_to_final(self) -> None:
        item = _item({"dialogue_phase": "no_dialogue", "has_speech": False, "transcript_count": 0})
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        handled = orchestrator._advance_after_success(item, _analyze_job(item))

        self.assertTrue(handled)
        self.assertEqual(item.status, ReupQueueStatus.WAITING_FOR_METADATA)
        self.assertEqual(item.metadata_json.get("pipeline_step"), "ready_final")

    def test_measured_no_dialogue_keeps_rendering_when_mode_goes_to_render(self) -> None:
        item = _item({"dialogue_phase": "no_dialogue", "has_speech": False, "transcript_count": 0})
        item.metadata_json = {"pipeline_mode": "auto_to_render", "pipeline_step": "analyze_audio"}
        orchestrator = ReupPipelineOrchestrator(MagicMock())

        with patch.object(ReupPipelineOrchestrator, "_ensure_ocr", return_value=True) as ensure_ocr:
            handled = orchestrator._advance_after_success(item, _analyze_job(item))

        self.assertTrue(handled)
        ensure_ocr.assert_called_once()
        self.assertEqual(item.metadata_json.get("pipeline_step"), "ocr")


if __name__ == "__main__":
    unittest.main()
