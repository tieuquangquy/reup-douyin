from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.models.artifacts import TranscriptSegment, TranslationSegment
from src.models.ingestion import SourceVideo
from src.enums import TranscriptSegmentStatus
from src.audio_pipeline.translation_authority import validate_translation_authority
from src.tts_pipeline.errors import TtsPipelineError, TtsPipelineErrorCode
from src.tts_pipeline.types import TranslationInputSegment


class TranslationInputResolver:
    def __init__(self, db: Session):
        self.db = db

    def resolve(self, source_video_id: UUID) -> list[TranslationInputSegment]:
        rows = list(
            self.db.scalars(
                select(TranslationSegment)
                .join(
                    TranscriptSegment,
                    TranslationSegment.transcript_segment_id == TranscriptSegment.id,
                )
                .where(
                    TranslationSegment.source_video_id == source_video_id,
                    TranslationSegment.is_current.is_(True),
                    TranscriptSegment.source_video_id == source_video_id,
                    TranscriptSegment.is_current.is_(True),
                )
                .options(selectinload(TranslationSegment.transcript_segment))
                .order_by(TranslationSegment.segment_index.asc())
            )
        )
        if not rows:
            raise TtsPipelineError(TtsPipelineErrorCode.MISSING_TRANSLATION_SEGMENTS, "No current translation segments found")

        source_video = self.db.get(SourceVideo, source_video_id)
        authority = dict(
            (getattr(source_video, "metadata_json", None) or {}).get("translation_authority") or {}
        ) if isinstance(getattr(source_video, "metadata_json", None), dict) else {}
        if authority:
            transcript_rows = [
                row.transcript_segment
                for row in rows
                if getattr(row, "transcript_segment", None) is not None
            ]
            valid, reason = validate_translation_authority(
                authority,
                source_video_id=source_video_id,
                transcript_rows=transcript_rows,
                translation_rows=rows,
            )
            if not valid:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TTS_AUTHORITY_CHANGED,
                    "Translation draft no longer matches its transcript authority: "
                    f"{reason or 'unknown_reason'}",
                )
            if not bool(authority.get("tts_ready")):
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TRANSLATION_REVIEW_REQUIRED,
                    "Translation quality contract is not TTS-ready.",
                )

        segments: list[TranslationInputSegment] = []
        for row in rows:
            transcript = row.transcript_segment
            row_metadata = dict(getattr(row, "metadata_json", None) or {})
            adaptation = dict(row_metadata.get("duration_adaptation") or {})
            candidate_texts = tuple(
                dict.fromkeys(
                    str(candidate.get("text") or "").strip()
                    for candidate in list(adaptation.get("candidates") or [])
                    if isinstance(candidate, dict)
                    and str(candidate.get("text") or "").strip()
                    and bool(candidate.get("protected_tokens_ok", True))
                    and bool(candidate.get("tts_eligible", False))
                )
            )
            translation_v3 = dict(row_metadata.get("translation_v3") or {})
            v3_candidate_texts = tuple(
                dict.fromkeys(
                    str(candidate.get("text") or "").strip()
                    for candidate in list(translation_v3.get("candidate_evaluations") or [])
                    if isinstance(candidate, dict)
                    and bool(candidate.get("hard_valid"))
                    and bool(candidate.get("tts_eligible", False))
                    and str(candidate.get("text") or "").strip()
                )
            )
            candidate_texts = tuple(
                dict.fromkeys([*candidate_texts, *v3_candidate_texts])
            )
            flags = {
                str(value)
                for value in list((row.quality_flags_json or {}).get("flags") or [])
            }
            review_flags = flags.intersection(
                {
                    "machine_translate_recovery",
                    "translation_llm_unavailable",
                    "translation_gate_failed",
                    "translation_too_long_for_slot",
                    "duration_rewrite_no_safe_candidate",
                    "duration_adaptation_required",
                    "translation_v3_candidate_review",
                    "translation_selective_semantic_review",
                    "needs_operator_review",
                }
            )
            if review_flags and row.status != TranscriptSegmentStatus.APPROVED:
                raise TtsPipelineError(
                    TtsPipelineErrorCode.TRANSLATION_REVIEW_REQUIRED,
                    "Vietnamese translation requires operator review before TTS: "
                    f"segment_index={row.segment_index} flags={','.join(sorted(review_flags))}",
                )
            if not row.text.strip():
                raise TtsPipelineError(TtsPipelineErrorCode.MISSING_TRANSLATION_SEGMENTS, "Translation text is empty")
            if transcript.end_ms <= transcript.start_ms or transcript.start_ms < 0:
                raise TtsPipelineError(TtsPipelineErrorCode.INVALID_SEGMENT_TIMING, "Invalid transcript segment timing")
            timeline_budget_ms = int(transcript.end_ms) - int(transcript.start_ms)
            declared_budget_ms = int(row.duration_budget_ms or timeline_budget_ms)
            if declared_budget_ms != timeline_budget_ms:
                flags.add("duration_budget_rebound_to_current_timeline")
            segments.append(
                TranslationInputSegment(
                    translation_segment_id=row.id,
                    transcript_segment_id=transcript.id,
                    source_video_id=row.source_video_id,
                    segment_index=row.segment_index if row.segment_index is not None else transcript.segment_index,
                    start_ms=transcript.start_ms,
                    end_ms=transcript.end_ms,
                    translated_text=row.text,
                    # Current transcript timing is the physical assembly
                    # authority. A stale translation budget must never allow a
                    # clip longer than the slot NarrationAssembler will accept.
                    duration_budget_ms=timeline_budget_ms,
                    translation_version=row.version,
                    translation_preset=row.translation_preset,
                    quality_flags=list(flags),
                    translation_status=str(
                        getattr(row.status, "value", row.status) or ""
                    ),
                    source_text=str(getattr(transcript, "text", "") or ""),
                    speaker_label=getattr(transcript, "speaker_label", None),
                    member_translation_segment_ids=(row.id,),
                    member_transcript_segment_ids=(transcript.id,),
                    member_segment_indices=(
                        row.segment_index if row.segment_index is not None else transcript.segment_index,
                    ),
                    candidate_texts=candidate_texts,
                    original_start_ms=transcript.start_ms,
                    original_end_ms=transcript.end_ms,
                    source_prosody=_source_prosody_metadata(transcript),
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


def _source_prosody_metadata(transcript: TranscriptSegment) -> dict:
    """Recover cheap phrase/pause evidence from persisted local ASR metadata."""

    metadata = dict(getattr(transcript, "metadata_json", None) or {})
    raw = dict(metadata.get("raw_payload") or {})
    timestamps = raw.get("timestamps")
    if not isinstance(timestamps, list):
        sentence = raw.get("sentence")
        timestamps = dict(sentence).get("timestamp") if isinstance(sentence, dict) else []
    valid: list[tuple[float, float]] = []
    for item in list(timestamps or []):
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            start_ms = float(item[0])
            end_ms = float(item[1])
        except (TypeError, ValueError):
            continue
        if start_ms >= 0 and end_ms > start_ms:
            valid.append((start_ms, end_ms))
    articulation_ms = sum(end - start for start, end in valid)
    internal_pause_ms = sum(
        max(0.0, valid[index][0] - valid[index - 1][1])
        for index in range(1, len(valid))
    )
    slot_ms = max(1, int(transcript.end_ms) - int(transcript.start_ms))
    source_text = str(getattr(transcript, "text", "") or "").strip()
    return {
        "schema_version": "source_phrase_prosody_v1",
        "word_timestamp_count": len(valid),
        "articulation_ms": round(articulation_ms, 3),
        "internal_pause_ms": round(internal_pause_ms, 3),
        "internal_pause_ratio": round(internal_pause_ms / slot_ms, 6),
        "phrase_end_punctuation": source_text[-1:] if source_text[-1:] in "。！？!?；;" else "",
        "speaker_label": str(getattr(transcript, "speaker_label", None) or "") or None,
        "authority": "local_asr_word_timestamps" if valid else "segment_timeline_only",
    }
