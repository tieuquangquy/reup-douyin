from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.models.artifacts import TranslationSegment
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TranslationInputSegment


class TranslationInputResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve(self, source_video_id: UUID) -> list[TranslationInputSegment]:
        rows = list(
            self.db.scalars(
                select(TranslationSegment)
                .where(
                    TranslationSegment.source_video_id == source_video_id,
                    TranslationSegment.is_current.is_(True),
                )
                .options(selectinload(TranslationSegment.transcript_segment))
                .order_by(TranslationSegment.segment_index.asc())
            )
        )
        if not rows:
            raise TtsPipelineError(TtsPipelineErrorCode.MISSING_TRANSLATION_SEGMENTS, "No current translation segments found")

        segments: list[TranslationInputSegment] = []
        for row in rows:
            transcript = row.transcript_segment
            if not row.text.strip():
                raise TtsPipelineError(TtsPipelineErrorCode.MISSING_TRANSLATION_SEGMENTS, "Translation text is empty")
            if transcript.end_ms <= transcript.start_ms or transcript.start_ms < 0:
                raise TtsPipelineError(TtsPipelineErrorCode.INVALID_SEGMENT_TIMING, "Invalid transcript segment timing")
            segments.append(
                TranslationInputSegment(
                    translation_segment_id=row.id,
                    transcript_segment_id=transcript.id,
                    source_video_id=row.source_video_id,
                    segment_index=row.segment_index if row.segment_index is not None else transcript.segment_index,
                    start_ms=transcript.start_ms,
                    end_ms=transcript.end_ms,
                    translated_text=row.text,
                    duration_budget_ms=row.duration_budget_ms or (transcript.end_ms - transcript.start_ms),
                    translation_version=row.version,
                    translation_preset=row.translation_preset,
                    quality_flags=(row.quality_flags_json or {}).get("flags", []),
                )
            )
        _validate_order(segments)
        return sorted(segments, key=lambda item: (item.start_ms, item.segment_index))


def _validate_order(segments: list[TranslationInputSegment]) -> None:
    previous_end = -1
    for segment in sorted(segments, key=lambda item: item.start_ms):
        if segment.start_ms < previous_end:
            raise TtsPipelineError(TtsPipelineErrorCode.INVALID_SEGMENT_TIMING, "Translation segment timing overlaps")
        previous_end = segment.end_ms
