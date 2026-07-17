from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.audio_pipeline.services.transcript_builder import normalize_source_text
from src.audio_pipeline.types import TranslationPreset
from src.enums import TranscriptSegmentStatus
from src.models.artifacts import TranscriptSegment, TranslationSegment


@dataclass(frozen=True)
class SegmentEdit:
    transcript_segment_id: UUID
    translation_segment_id: UUID | None
    start_ms: int
    end_ms: int
    source_text: str
    translated_text: str
    status: TranscriptSegmentStatus = TranscriptSegmentStatus.NEEDS_REVIEW


class TranscriptEditService:
    def __init__(self, db: Session):
        self.db = db

    def save_draft(self, source_video_id: UUID, edits: list[SegmentEdit]) -> dict:
        self._validate_batch_timing(source_video_id, edits)
        changed = 0
        for edit in edits:
            transcript = self._current_transcript(source_video_id, edit.transcript_segment_id)
            self._validate_timing(edit.start_ms, edit.end_ms)
            transcript.start_ms = edit.start_ms
            transcript.end_ms = edit.end_ms
            transcript.text = edit.source_text.strip()
            transcript.normalized_text = normalize_source_text(edit.source_text)
            transcript.status = edit.status
            transcript.metadata_json = {
                **(transcript.metadata_json or {}),
                "edited_in_transcript_editor": True,
            }
            if edit.translation_segment_id:
                translation = self._current_translation(source_video_id, edit.translation_segment_id)
                translation.text = edit.translated_text.strip()
                translation.duration_budget_ms = edit.end_ms - edit.start_ms
                translation.status = edit.status
                translation.metadata_json = {
                    **(translation.metadata_json or {}),
                    "edited_in_transcript_editor": True,
                }
            changed += 1
        self.db.commit()
        return {"updated_segments": changed}

    def merge_segments(self, source_video_id: UUID, left_transcript_id: UUID, right_transcript_id: UUID) -> dict:
        left = self._current_transcript(source_video_id, left_transcript_id)
        right = self._current_transcript(source_video_id, right_transcript_id)
        if right.start_ms < left.start_ms:
            left, right = right, left
        left.end_ms = max(left.end_ms, right.end_ms)
        left.text = " ".join(part.strip() for part in [left.text, right.text] if part.strip())
        left.normalized_text = normalize_source_text(left.text)
        left.status = TranscriptSegmentStatus.NEEDS_REVIEW
        left.difficulty_flags_json = _merge_flag_payload(left.difficulty_flags_json, right.difficulty_flags_json, "merged_segment")
        left.metadata_json = {**(left.metadata_json or {}), "merged_from_segment_id": str(right.id)}
        right.is_current = False

        left_translation = self._current_translation_for_transcript(left.id)
        right_translation = self._current_translation_for_transcript(right.id)
        if left_translation and right_translation:
            left_translation.text = " ".join(
                part.strip() for part in [left_translation.text, right_translation.text] if part.strip()
            )
            left_translation.duration_budget_ms = left.end_ms - left.start_ms
            left_translation.status = TranscriptSegmentStatus.NEEDS_REVIEW
            left_translation.quality_flags_json = _merge_flag_payload(
                left_translation.quality_flags_json,
                right_translation.quality_flags_json,
                "merged_segment",
            )
            left_translation.metadata_json = {
                **(left_translation.metadata_json or {}),
                "merged_from_translation_id": str(right_translation.id),
            }
            right_translation.is_current = False
        self.db.commit()
        return {"kept_transcript_segment_id": str(left.id), "archived_transcript_segment_id": str(right.id)}

    def split_segment(
        self,
        source_video_id: UUID,
        transcript_segment_id: UUID,
        *,
        split_ms: int,
        left_source_text: str,
        right_source_text: str,
        left_translated_text: str,
        right_translated_text: str,
    ) -> dict:
        original = self._current_transcript(source_video_id, transcript_segment_id)
        if split_ms <= original.start_ms or split_ms >= original.end_ms:
            raise ValueError("split_ms must be inside segment timing")
        original_translation = self._current_translation_for_transcript(original.id)
        next_index = self._next_segment_index(source_video_id)
        original_end_ms = original.end_ms

        original.end_ms = split_ms
        original.text = left_source_text.strip()
        original.normalized_text = normalize_source_text(left_source_text)
        original.status = TranscriptSegmentStatus.NEEDS_REVIEW
        original.difficulty_flags_json = _merge_flag_payload(original.difficulty_flags_json, None, "split_segment")
        if original_translation:
            original_translation.text = left_translated_text.strip()
            original_translation.duration_budget_ms = original.end_ms - original.start_ms
            original_translation.status = TranscriptSegmentStatus.NEEDS_REVIEW
            original_translation.quality_flags_json = _merge_flag_payload(
                original_translation.quality_flags_json,
                None,
                "split_segment",
            )

        new_transcript = TranscriptSegment(
            workspace_id=original.workspace_id,
            source_video_id=original.source_video_id,
            segment_index=next_index,
            version=original.version,
            start_ms=split_ms,
            end_ms=original_end_ms,
            text=right_source_text.strip(),
            normalized_text=normalize_source_text(right_source_text),
            language_code=original.language_code,
            status=TranscriptSegmentStatus.NEEDS_REVIEW,
            confidence=original.confidence,
            speaker_label=original.speaker_label,
            difficulty_flags_json={"flags": ["split_segment"]},
            analysis_version=original.analysis_version,
            created_by_job_id=original.created_by_job_id,
            is_current=True,
            metadata_json={"split_from_segment_id": str(original.id)},
        )
        self.db.add(new_transcript)
        self.db.flush()

        if original_translation:
            new_translation = TranslationSegment(
                workspace_id=original_translation.workspace_id,
                source_video_id=original_translation.source_video_id,
                transcript_segment_id=new_transcript.id,
                language_code=original_translation.language_code,
                version=original_translation.version,
                text=right_translated_text.strip(),
                status=TranscriptSegmentStatus.NEEDS_REVIEW,
                segment_index=next_index,
                translation_preset=original_translation.translation_preset,
                duration_budget_ms=new_transcript.end_ms - new_transcript.start_ms,
                estimated_tts_duration_ms=None,
                quality_flags_json={"flags": ["split_segment"]},
                created_by_job_id=original_translation.created_by_job_id,
                is_current=True,
                metadata_json={"split_from_translation_id": str(original_translation.id)},
            )
            self.db.add(new_translation)
        self.db.commit()
        return {"updated_transcript_segment_id": str(original.id), "created_transcript_segment_id": str(new_transcript.id)}

    def create_rerun_job(
        self,
        source_video_id: UUID,
        *,
        translation_preset: TranslationPreset,
        force_refresh: bool = True,
        require_source_approved: bool = True,
    ):
        """Phase B only: literal/style translation from current beats — never re-runs FunASR."""
        from src.audio_pipeline.services.audio_analysis_service import AudioAnalysisService

        return AudioAnalysisService(self.db).create_translation_job(
            source_video_id,
            translation_preset=translation_preset or TranslationPreset.LITERAL_SAFE,
            force_refresh=force_refresh,
            require_source_approved=require_source_approved,
        )

    def _current_transcript(self, source_video_id: UUID, segment_id: UUID) -> TranscriptSegment:
        row = self.db.scalar(
            select(TranscriptSegment).where(
                TranscriptSegment.id == segment_id,
                TranscriptSegment.source_video_id == source_video_id,
                TranscriptSegment.is_current.is_(True),
            )
        )
        if row is None:
            raise ValueError("Transcript segment not found")
        return row

    def _current_translation(self, source_video_id: UUID, segment_id: UUID) -> TranslationSegment:
        row = self.db.scalar(
            select(TranslationSegment).where(
                TranslationSegment.id == segment_id,
                TranslationSegment.source_video_id == source_video_id,
                TranslationSegment.is_current.is_(True),
            )
        )
        if row is None:
            raise ValueError("Translation segment not found")
        return row

    def _current_translation_for_transcript(self, transcript_segment_id: UUID) -> TranslationSegment | None:
        return self.db.scalar(
            select(TranslationSegment).where(
                TranslationSegment.transcript_segment_id == transcript_segment_id,
                TranslationSegment.is_current.is_(True),
            )
        )

    def _next_segment_index(self, source_video_id: UUID) -> int:
        max_index = self.db.scalar(
            select(func.max(TranscriptSegment.segment_index)).where(TranscriptSegment.source_video_id == source_video_id)
        )
        return (max_index or 0) + 1

    def _validate_timing(self, start_ms: int, end_ms: int) -> None:
        if start_ms < 0:
            raise ValueError("start_ms must be non-negative")
        if end_ms <= start_ms:
            raise ValueError("end_ms must be greater than start_ms")

    def _validate_batch_timing(self, source_video_id: UUID, edits: list[SegmentEdit]) -> None:
        edit_by_id = {edit.transcript_segment_id: edit for edit in edits}
        segments = list(
            self.db.scalars(
                select(TranscriptSegment)
                .where(
                    TranscriptSegment.source_video_id == source_video_id,
                    TranscriptSegment.is_current.is_(True),
                )
                .order_by(TranscriptSegment.start_ms.asc())
            )
        )
        timeline: list[tuple[int, int, UUID]] = []
        for segment in segments:
            edit = edit_by_id.get(segment.id)
            start_ms = edit.start_ms if edit else segment.start_ms
            end_ms = edit.end_ms if edit else segment.end_ms
            self._validate_timing(start_ms, end_ms)
            timeline.append((start_ms, end_ms, segment.id))

        timeline.sort(key=lambda item: (item[0], item[1]))
        for previous, current in zip(timeline, timeline[1:]):
            if current[0] < previous[1]:
                raise ValueError("segment timing overlaps another current segment")


def _merge_flag_payload(left: dict | None, right: dict | None, extra: str) -> dict:
    flags = [*(left or {}).get("flags", []), *(right or {}).get("flags", []), extra]
    return {"flags": list(dict.fromkeys(flags))}
