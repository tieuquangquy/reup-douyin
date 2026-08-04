from __future__ import annotations

import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from src.audio_pipeline.services.dialogue_translation_review import (
    DialogueTranslationReviewError,
    _sha256_json,
    _supersede_active_approval,
    build_review_payload,
    verify_approval_payload,
    verify_review_payload,
)
from src.enums import TranscriptSegmentStatus


class DialogueTranslationReviewTests(unittest.TestCase):
    def _row(self):
        source_video_id = uuid4()
        transcript = SimpleNamespace(
            id=uuid4(),
            source_video_id=source_video_id,
            segment_index=0,
            version=2,
            start_ms=0,
            end_ms=4000,
            text="åŽŸæ–‡",
            normalized_text="åŽŸæ–‡",
            language_code="zh",
            status=TranscriptSegmentStatus.APPROVED,
            confidence=0.9,
            difficulty_flags_json={"flags": ["funasr"]},
            analysis_version="AUDIO_ANALYSIS_V1_RUN_2",
            created_by_job_id=uuid4(),
            is_current=True,
            metadata_json={"provider": "fixture"},
        )
        translation = SimpleNamespace(
            id=uuid4(),
            source_video_id=source_video_id,
            transcript_segment_id=transcript.id,
            transcript_segment=transcript,
            segment_index=0,
            version=3,
            language_code="vi",
            text="Báº£n dá»‹ch hiá»‡n táº¡i",
            status=TranscriptSegmentStatus.NEEDS_REVIEW,
            translation_preset="literal_safe",
            duration_budget_ms=4000,
            estimated_tts_duration_ms=4200,
            quality_flags_json={"flags": ["workspace_translation_prompt"]},
            created_by_job_id=uuid4(),
            is_current=True,
            metadata_json={"speech_budget": {"status": "fits_budget"}},
        )
        return source_video_id, translation

    def test_builds_self_hashed_pending_review_with_both_authorities(self) -> None:
        source_video_id, row = self._row()
        payload = build_review_payload(
            [row],
            source_video_id=source_video_id,
            suggested_text_by_translation_id={str(row.id): "Báº£n dá»‹ch Ä‘á» xuáº¥t."},
            authority_refs=[{"path": "phase3.json", "sha256": "a" * 64}],
            created_at="2026-07-28T00:00:00+00:00",
        )
        verify_review_payload(payload)
        self.assertEqual(payload["status"], "PENDING_OPERATOR_REVIEW")
        self.assertFalse(payload["operator_approval_written"])
        segment = payload["segments"][0]
        self.assertEqual(segment["timing"]["required_rate_to_fit"], 1.05)
        self.assertEqual(len(segment["translation_authority_sha256"]), 64)
        self.assertEqual(len(segment["transcript_authority_sha256"]), 64)
        self.assertIsNotNone(segment["suggested_review_budget"])

    def test_tampered_artifact_fails_verification(self) -> None:
        source_video_id, row = self._row()
        payload = build_review_payload([row], source_video_id=source_video_id)
        payload["segments"][0]["current_candidate_text"] = "tampered"
        with self.assertRaises(DialogueTranslationReviewError):
            verify_review_payload(payload)

    def test_approval_verifier_rejects_tampering(self) -> None:
        approval = {
            "schema_version": "dialogue_translation_approval_v1",
            "status": "DIALOGUE_TRANSLATION_APPROVED",
            "operator_approval_written": True,
            "segments": [],
        }
        approval["approval_sha256"] = _sha256_json(approval)
        verify_approval_payload(approval)
        approval["status"] = "REJECTED"
        with self.assertRaises(DialogueTranslationReviewError):
            verify_approval_payload(approval)

    def test_superseding_approval_preserves_immutable_history(self) -> None:
        source_video_id, row = self._row()
        prior_review = build_review_payload(
            [row],
            source_video_id=source_video_id,
            created_at="2026-07-28T00:00:00+00:00",
        )
        prior_approval = {
            "schema_version": "dialogue_translation_approval_v1",
            "status": "DIALOGUE_TRANSLATION_APPROVED",
            "operator_approval_written": True,
            "review_ref": {
                "artifact_sha256": prior_review["artifact_sha256"],
            },
            "segments": [],
        }
        prior_approval["approval_sha256"] = _sha256_json(prior_approval)
        next_review = build_review_payload(
            [row],
            source_video_id=source_video_id,
            suggested_text_by_translation_id={str(row.id): "Báº£n dá»‹ch ngáº¯n hÆ¡n."},
            supersedes={
                "reason": "timing_fit_blocked",
                "review_artifact_sha256": prior_review["artifact_sha256"],
                "approval_sha256": prior_approval["approval_sha256"],
            },
            created_at="2026-07-29T00:00:00+00:00",
        )
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "phase4_dialogue_translation_review.json").write_text(
                json.dumps(prior_review), encoding="utf-8"
            )
            (root / "phase4_dialogue_translation_approval.json").write_text(
                json.dumps(prior_approval), encoding="utf-8"
            )

            result = _supersede_active_approval(
                root,
                prior_review=prior_review,
                prior_approval=prior_approval,
                next_review=next_review,
                reason="timing_fit_blocked",
            )

            self.assertEqual(result["status"], "APPROVED_REVIEW_SUPERSEDED")
            self.assertFalse(
                (root / "phase4_dialogue_translation_approval.json").exists()
            )
            history = root / "dialogue_translation_review_history"
            self.assertTrue(
                (history / f"review_{prior_review['artifact_sha256']}.json").is_file()
            )
            self.assertTrue(
                (history / f"approval_{prior_approval['approval_sha256']}.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
