"""Translation reruns preserve approved history and retries stay idempotent."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService
from src.audio_pipeline.types import TranslationDraftSegment, TranslationPreset
from src.enums import TranscriptSegmentStatus


class TranslationPersistUpsertTests(unittest.TestCase):
    def test_rerun_inserts_new_version_instead_of_overwriting_existing_translation(self) -> None:
        workspace_id = uuid4()
        source_video_id = uuid4()
        transcript_id = uuid4()
        existing = SimpleNamespace(
            id=uuid4(),
            workspace_id=workspace_id,
            source_video_id=source_video_id,
            transcript_segment_id=transcript_id,
            language_code="vi",
            version=3,
            text="ban cu",
            status=TranscriptSegmentStatus.DRAFT,
            segment_index=0,
            translation_preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_ms=1000,
            estimated_tts_duration_ms=900,
            quality_flags_json={"flags": ["old"]},
            created_by_job_id=None,
            is_current=False,
            metadata_json={},
        )
        db = MagicMock()
        db.scalar.side_effect = [None, existing.version]
        service = AudioAnalysisService(db=db, storage=MagicMock())
        source_video = SimpleNamespace(id=source_video_id, workspace_id=workspace_id)
        transcript = SimpleNamespace(
            id=transcript_id,
            segment_index=0,
            version=3,
        )
        job_id = uuid4()
        drafts = [
            TranslationDraftSegment(
                segment_index=0,
                translated_text="ban moi tu MyMemory",
                translation_preset=TranslationPreset.LITERAL_SAFE,
                duration_budget_seconds=4.6,
                estimated_tts_duration_seconds=5.0,
                quality_flags=["machine_translate_primary"],
                metadata={"provider": "mymemory"},
            )
        ]

        rows = service._persist_translations(source_video, [transcript], drafts, job_id)

        self.assertEqual(len(rows), 1)
        self.assertIsNot(rows[0], existing)
        self.assertEqual(existing.text, "ban cu")
        db.add.assert_called_once()
        created = db.add.call_args.args[0]
        self.assertEqual(created.version, 4)
        self.assertEqual(created.text, "ban moi tu MyMemory")
        self.assertTrue(created.is_current)
        self.assertEqual(created.created_by_job_id, job_id)
        self.assertEqual(created.quality_flags_json, {"flags": ["machine_translate_primary"]})
        db.flush.assert_called_once()

    def test_same_job_retry_updates_its_own_translation_row(self) -> None:
        job_id = uuid4()
        existing = SimpleNamespace(
            id=uuid4(),
            version=4,
            text="partial",
            status=TranscriptSegmentStatus.NEEDS_REVIEW,
            segment_index=0,
            translation_preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_ms=1000,
            estimated_tts_duration_ms=900,
            quality_flags_json={"flags": []},
            created_by_job_id=job_id,
            is_current=False,
            metadata_json={},
        )
        db = MagicMock()
        db.scalar.return_value = existing
        service = AudioAnalysisService(db=db, storage=MagicMock())
        source_video = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
        transcript = SimpleNamespace(id=uuid4(), segment_index=0, version=3)
        draft = TranslationDraftSegment(
            segment_index=0,
            translated_text="completed",
            translation_preset=TranslationPreset.LITERAL_SAFE,
            duration_budget_seconds=2.0,
            estimated_tts_duration_seconds=1.5,
            quality_flags=["duration_rewrite_applied"],
            metadata={"duration_adaptation": {"decision": "review_candidate_selected"}},
        )

        rows = service._persist_translations(
            source_video,
            [transcript],
            [draft],
            job_id,
        )

        self.assertIs(rows[0], existing)
        self.assertEqual(existing.text, "completed")
        self.assertTrue(existing.is_current)
        db.add.assert_not_called()

    def test_persist_translations_inserts_when_no_existing_row(self) -> None:
        db = MagicMock()
        db.scalar.side_effect = [None, None]
        service = AudioAnalysisService(db=db, storage=MagicMock())
        source_video = SimpleNamespace(id=uuid4(), workspace_id=uuid4())
        transcript = SimpleNamespace(id=uuid4(), segment_index=0, version=1)
        drafts = [
            TranslationDraftSegment(
                segment_index=0,
                translated_text="moi",
                translation_preset=TranslationPreset.LITERAL_SAFE,
                duration_budget_seconds=2.0,
                estimated_tts_duration_seconds=1.5,
                quality_flags=[],
                metadata={},
            )
        ]

        rows = service._persist_translations(source_video, [transcript], drafts, uuid4())

        self.assertEqual(len(rows), 1)
        db.add.assert_called_once()
        self.assertEqual(db.add.call_args.args[0].text, "moi")
        self.assertTrue(db.add.call_args.args[0].is_current)


if __name__ == "__main__":
    unittest.main()
