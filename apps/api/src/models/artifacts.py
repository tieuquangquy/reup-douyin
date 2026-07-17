from __future__ import annotations

from uuid import UUID

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.db.base import BaseModel
from src.enums import OcrObjectStatus, TranscriptSegmentStatus


class TranscriptSegment(BaseModel):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint(
            "source_video_id",
            "segment_index",
            "version",
            name="uq_transcript_segments_video_index_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    language_code: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[TranscriptSegmentStatus] = mapped_column(
        Enum(TranscriptSegmentStatus, name="transcript_segment_status"),
        default=TranscriptSegmentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    speaker_label: Mapped[str | None] = mapped_column(String(80))
    difficulty_flags_json: Mapped[dict | None] = mapped_column(JSONB)
    analysis_version: Mapped[str | None] = mapped_column(String(80), index=True)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="transcript_segments")
    translations: Mapped[list[TranslationSegment]] = relationship(back_populates="transcript_segment")


class TranslationSegment(BaseModel):
    __tablename__ = "translation_segments"
    __table_args__ = (
        UniqueConstraint(
            "transcript_segment_id",
            "language_code",
            "version",
            name="uq_translation_segments_transcript_language_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    transcript_segment_id: Mapped[UUID] = mapped_column(
        ForeignKey("transcript_segments.id"),
        index=True,
    )
    language_code: Mapped[str] = mapped_column(String(16), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TranscriptSegmentStatus] = mapped_column(
        Enum(TranscriptSegmentStatus, name="transcript_segment_status"),
        default=TranscriptSegmentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    segment_index: Mapped[int | None] = mapped_column(Integer, index=True)
    translation_preset: Mapped[str | None] = mapped_column(String(80), index=True)
    duration_budget_ms: Mapped[int | None] = mapped_column(Integer)
    estimated_tts_duration_ms: Mapped[int | None] = mapped_column(Integer)
    quality_flags_json: Mapped[dict | None] = mapped_column(JSONB)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="translation_segments")
    transcript_segment: Mapped[TranscriptSegment] = relationship(back_populates="translations")
    subtitles: Mapped[list[SubtitleSegment]] = relationship(back_populates="translation_segment")


class SubtitleSegment(BaseModel):
    __tablename__ = "subtitle_segments"
    __table_args__ = (
        UniqueConstraint(
            "source_video_id",
            "segment_index",
            "version",
            name="uq_subtitle_segments_video_index_version",
        ),
    )

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    translation_segment_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("translation_segments.id"),
        index=True,
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[TranscriptSegmentStatus] = mapped_column(
        Enum(TranscriptSegmentStatus, name="transcript_segment_status"),
        default=TranscriptSegmentStatus.DRAFT,
        nullable=False,
        index=True,
    )
    style_json: Mapped[dict | None] = mapped_column(JSONB)
    layout_mode: Mapped[str | None] = mapped_column(String(80), index=True)
    track_kind: Mapped[str | None] = mapped_column(String(80), index=True)
    review_flags_json: Mapped[dict | None] = mapped_column(JSONB)
    subtitle_version: Mapped[str | None] = mapped_column(String(80), index=True)
    created_by_job_id: Mapped[UUID | None] = mapped_column(ForeignKey("jobs.id"), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="subtitle_segments")
    translation_segment: Mapped[TranslationSegment | None] = relationship(back_populates="subtitles")


class OcrTextObject(BaseModel):
    __tablename__ = "ocr_text_objects"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str | None] = mapped_column(Text)
    language_code: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[OcrObjectStatus] = mapped_column(
        Enum(OcrObjectStatus, name="ocr_object_status"),
        default=OcrObjectStatus.DETECTED,
        nullable=False,
        index=True,
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    first_seen_ms: Mapped[int | None] = mapped_column(Integer)
    last_seen_ms: Mapped[int | None] = mapped_column(Integer)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    source_video: Mapped["SourceVideo"] = relationship(back_populates="ocr_text_objects")
    frame_detections: Mapped[list[OcrFrameDetection]] = relationship(back_populates="ocr_text_object")


class OcrFrameDetection(BaseModel):
    __tablename__ = "ocr_frame_detections"

    workspace_id: Mapped[UUID] = mapped_column(ForeignKey("workspaces.id"), index=True)
    source_video_id: Mapped[UUID] = mapped_column(ForeignKey("source_videos.id"), index=True)
    ocr_text_object_id: Mapped[UUID] = mapped_column(ForeignKey("ocr_text_objects.id"), index=True)
    frame_time_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    x: Mapped[float] = mapped_column(Float, nullable=False)
    y: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    raw_payload_json: Mapped[dict | None] = mapped_column(JSONB)

    ocr_text_object: Mapped[OcrTextObject] = relationship(back_populates="frame_detections")
