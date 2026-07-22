from __future__ import annotations

import re
from calendar import monthrange
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.enums import CaptureSessionStatus, CapturedItemStatus, IntakeEvaluationStatus, SourcePlatformEnum
from src.services.douyin_metadata_normalization import (
    build_data_quality_flags,
    calculate_engagement,
    normalize_douyin_count,
    normalize_douyin_duration,
    normalize_douyin_engagement_count,
    normalize_douyin_estimated_views,
    normalize_douyin_posted,
)

MetadataStatus = Literal["pending_hydration", "complete", "partial", "missing", "failed"]
MetadataGroupStatus = Literal["captured", "missing", "failed", "pending"]
CaptureInboxStudioStatus = Literal["all", "ready", "promoted", "duplicate", "needs_action", "failed"]


class CaptureInboxReconciliationResponse(BaseModel):
    visible_item_count: int = 0
    captured_item_count: int = 0
    normalized_item_count: int = 0
    duplicate_item_count: int = 0
    ready_item_count: int = 0
    needs_action_count: int = 0
    skipped_item_count: int = 0
    promoted_item_count: int = 0
    candidate_created_count: int = 0
    failed_item_count: int = 0


class CapturedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    capture_session_id: UUID
    source_platform: SourcePlatformEnum
    status: CapturedItemStatus
    raw_item_index: int
    source_profile_external_id: str | None = None
    profile_url: str | None = None
    source_video_external_id: str | None = None
    aweme_id: str | None = None
    source_url: str | None = None
    share_url: str | None = None
    caption: str | None = None
    title: str | None = None
    poster_aspect_ratio: float | None = None
    duration_seconds: float | None = None
    duration_text_raw: str | None = None
    duration_text: str | None = None
    duration_parse_confidence: Literal["high", "medium", "low", "none"] = "none"
    posted_at: datetime | None = None
    posted_text: str | None = None
    posted_text_raw: str | None = None
    posted_display: str | None = None
    posted_parse_confidence: Literal["high", "medium", "low", "none"] = "none"
    thumbnail_url: str | None = None
    view_count: int | None = None
    view_count_text: str | None = None
    estimated_views_text_raw: str | None = None
    estimated_views_display: str | None = None
    estimated_views_min: int | None = None
    estimated_views_max: int | None = None
    estimated_views_mid: int | None = None
    estimated_views_parse_confidence: Literal["high", "medium", "low", "none"] = "none"
    like_count: int | None = None
    like_count_text: str | None = None
    comment_count: int | None = None
    comment_count_text: str | None = None
    share_count: int | None = None
    share_count_text: str | None = None
    favorite_count: int | None = None
    favorite_count_text: str | None = None
    follower_count: int | None = None
    follower_count_text: str | None = None
    engagement_score: int | None = None
    engagement_rate: float | None = None
    engagement_rate_basis: Literal["estimated_views_mid", "view_count", "none"] = "none"
    has_thumbnail: bool = False
    has_posted: bool = False
    has_duration: bool = False
    has_views: bool = False
    has_likes: bool = False
    has_comments: bool = False
    has_shares: bool = False
    has_all_core_metadata: bool = False
    missing_metadata_fields: list[str] = Field(default_factory=list)
    thumbnail_source: Literal["network_json", "dom_fallback", "detail_hydrate", "profile_card", "video_poster", "profile_card_image", "modal_img", "og_image", "missing"] | None = None
    posted_source: Literal["network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_snapshot", "existing_canonical", "missing", "fallback_none", "modal_author_row", "direct_publish_time", "embedded_aweme_json", "profile_card"] | None = None
    duration_source: Literal["network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"] | None = None
    view_count_source: Literal["network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"] | None = None
    like_count_source: Literal["network_json", "detail_hydrate", "dom_detail_modal", "dom_profile_card_fallback", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"] | None = None
    comment_count_source: Literal["network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "dom_zero_sentinel", "existing_canonical", "missing", "fallback_none"] | None = None
    share_count_source: Literal["network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "dom_zero_sentinel", "existing_canonical", "missing", "fallback_none"] | None = None
    engagement_rate_source: Literal["derived_from_counts", "derived_from_canonical_counts", "network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"] | None = None
    has_speech: bool | None = None
    text_density: Literal["low", "medium", "high"] | None = None
    has_heavy_watermark: bool | None = None
    processing_complexity: Literal["low", "medium", "high", "blocking"] | None = None
    copyright_risk: Literal["low", "medium", "high", "true"] | None = None
    preview_url: str | None = None
    preview_status: Literal["ready", "pending", "missing"] | None = None
    source_link_status: Literal["captured", "missing"] | None = None
    media_asset_status: Literal["not_generated", "ready", "failed"] | None = None
    media_status: Literal["ready", "pending", "missing", "source_link_captured"] | None = None
    preview_ready: bool = False
    media_ready: bool = False
    readiness_reasons_json: list[Any] | None = None
    dedupe_key: str | None = None
    duplicate_of_item_id: UUID | None = None
    existing_source_video_id: UUID | None = None
    promoted_source_video_id: UUID | None = None
    promoted_video_candidate_id: UUID | None = None
    promoted_crawl_session_id: UUID | None = None
    enrichment_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None
    intake_evaluation_status: IntakeEvaluationStatus = IntakeEvaluationStatus.MISSING_REQUIREMENTS
    matches_intake: bool | None = None
    intake_failed_rules_json: list[str] | None = None
    intake_missing_requirements_json: list[str] | None = None
    intake_filter_version: str | None = None
    intake_preset_name: str | None = None
    last_intake_evaluated_at: datetime | None = None
    intake_evaluation_error: str | None = None
    excluded_reason: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    raw_payload_json: dict[str, Any] = Field(default_factory=dict)
    metadata_status: MetadataStatus = "pending_hydration"
    time_status: MetadataGroupStatus = "pending"
    performance_status: MetadataGroupStatus = "pending"
    processing_fit_status: MetadataGroupStatus = "pending"
    metadata_missing_reason: str | None = None
    time_missing_reason: str | None = None
    performance_missing_reason: str | None = None
    processing_fit_missing_reason: str | None = None
    metadata_source_summary: str | None = None
    last_metadata_hydrated_at: datetime | None = None
    raw_evidence_summary: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def hydrate_card_grid_metadata(self) -> "CapturedItemResponse":
        metadata = self.metadata_json or {}
        raw_payload = self.raw_payload_json or {}
        stats = raw_payload.get("statistics") if isinstance(raw_payload.get("statistics"), dict) else {}
        self.aweme_id = self.source_video_external_id
        resolved_title = _capture_item_title_from_payloads(
            caption=self.caption,
            metadata=metadata,
            raw_payload=raw_payload,
            aweme_id=self.source_video_external_id,
        )
        self.caption = self.caption or resolved_title
        self.title = resolved_title
        self.poster_aspect_ratio = _float_metadata(metadata, raw_payload, key="poster_aspect_ratio")
        self.duration_seconds = _float_metadata(metadata, raw_payload, key="duration_seconds")
        self.duration_text_raw = _string_metadata(metadata, raw_payload, key="duration_text_raw") or _string_metadata(metadata, raw_payload, key="duration_text")
        self.duration_text = _string_metadata(metadata, raw_payload, key="duration_text")
        self.posted_at = _datetime_metadata(metadata, raw_payload, key="posted_at")
        self.posted_text_raw = _string_metadata(metadata, raw_payload, key="posted_text_raw")
        self.posted_display = _string_metadata(metadata, raw_payload, key="posted_display")
        self.posted_text = self.posted_display or _string_metadata(metadata, raw_payload, key="posted_text")
        lazy_posted = _lazy_normalize_legacy_posted(
            posted_at=self.posted_at,
            posted_text=self.posted_text,
            posted_text_raw=self.posted_text_raw,
            posted_display=self.posted_display,
            reference_time=self.updated_at or self.created_at,
        )
        self.posted_at = lazy_posted["posted_at"]
        self.posted_text_raw = lazy_posted["posted_text_raw"]
        self.posted_display = lazy_posted["posted_display"]
        self.posted_text = lazy_posted["posted_text"]
        self.view_count = _int_metadata(metadata, raw_payload, stats, key="view_count", alternate_key="play_count")
        self.view_count_text = _string_metadata(metadata, raw_payload, key="view_count_text")
        self.like_count = _int_metadata(metadata, raw_payload, stats, key="like_count", alternate_key="digg_count")
        self.like_count_text = _string_metadata(metadata, raw_payload, key="like_count_text")
        self.comment_count = _int_metadata(metadata, raw_payload, stats, key="comment_count")
        self.comment_count_text = _string_metadata(metadata, raw_payload, key="comment_count_text")
        self.share_count = _int_metadata(metadata, raw_payload, stats, key="share_count")
        self.share_count_text = _string_metadata(metadata, raw_payload, key="share_count_text")
        self.favorite_count = _int_metadata(metadata, raw_payload, stats, key="favorite_count", alternate_key="collect_count")
        self.favorite_count_text = _string_metadata(metadata, raw_payload, key="favorite_count_text")
        thumbnail_source = _string_metadata(metadata, raw_payload, key="thumbnail_source")
        self.thumbnail_source = thumbnail_source if thumbnail_source in {"network_json", "dom_fallback", "detail_hydrate", "profile_card", "video_poster", "profile_card_image", "modal_img", "og_image", "missing"} else None
        posted_source = _string_metadata(metadata, raw_payload, key="posted_source")
        self.posted_source = posted_source if posted_source in {"network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_snapshot", "existing_canonical", "missing", "fallback_none", "modal_author_row", "modal_author_row_profile_link", "direct_publish_time", "embedded_aweme_json", "profile_card"} else None
        self._hydrate_phase22d_normalized_fields(metadata=metadata, raw_payload=raw_payload, stats=stats)
        duration_source = _string_metadata(metadata, raw_payload, key="duration_source")
        self.duration_source = duration_source if duration_source in {"network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"} else None
        view_count_source = _string_metadata(metadata, raw_payload, key="view_count_source")
        self.view_count_source = view_count_source if view_count_source in {"network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"} else None
        like_count_source = _string_metadata(metadata, raw_payload, key="like_count_source")
        self.like_count_source = like_count_source if like_count_source in {"network_json", "detail_hydrate", "dom_detail_modal", "dom_profile_card_fallback", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"} else None
        comment_count_source = _string_metadata(metadata, raw_payload, key="comment_count_source")
        self.comment_count_source = comment_count_source if comment_count_source in {"network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "dom_zero_sentinel", "existing_canonical", "missing", "fallback_none"} else None
        share_count_source = _string_metadata(metadata, raw_payload, key="share_count_source")
        self.share_count_source = share_count_source if share_count_source in {"network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "dom_zero_sentinel", "existing_canonical", "missing", "fallback_none"} else None
        engagement_rate_source = _string_metadata(metadata, raw_payload, key="engagement_rate_source")
        self.engagement_rate_source = engagement_rate_source if engagement_rate_source in {"derived_from_counts", "derived_from_canonical_counts", "network_json", "detail_hydrate", "dom_detail_modal", "dom_text", "dom_fallback", "dom_snapshot", "existing_canonical", "missing", "fallback_none"} else None
        self.has_speech = _bool_metadata(metadata, raw_payload, key="has_speech")
        text_density = _string_metadata(metadata, raw_payload, key="text_density")
        self.text_density = text_density if text_density in {"low", "medium", "high"} else None
        self.has_heavy_watermark = _bool_metadata(metadata, raw_payload, key="has_heavy_watermark")
        processing_complexity = _string_metadata(metadata, raw_payload, key="processing_complexity")
        self.processing_complexity = processing_complexity if processing_complexity in {"low", "medium", "high", "blocking"} else None
        copyright_risk = _string_metadata(metadata, raw_payload, key="copyright_risk")
        self.copyright_risk = copyright_risk if copyright_risk in {"low", "medium", "high", "true"} else None
        preview_status = _string_metadata(metadata, raw_payload, key="preview_status")
        self.preview_status = preview_status if preview_status in {"ready", "pending", "missing"} else ("ready" if self.preview_ready else "missing")
        source_link_status = _string_metadata(metadata, raw_payload, key="source_link_status")
        self.source_link_status = source_link_status if source_link_status in {"captured", "missing"} else ("captured" if self.source_url or self.share_url else "missing")
        media_asset_status = _string_metadata(metadata, raw_payload, key="media_asset_status")
        self.media_asset_status = media_asset_status if media_asset_status in {"not_generated", "ready", "failed"} else ("ready" if self.media_ready else "not_generated")
        media_status = _string_metadata(metadata, raw_payload, key="media_status")
        self.media_status = media_status if media_status in {"ready", "pending", "missing", "source_link_captured"} else ("ready" if self.media_asset_status == "ready" else ("source_link_captured" if self.source_link_status == "captured" else "missing"))
        self.raw_evidence_summary = metadata.get("raw_evidence_summary") if isinstance(metadata.get("raw_evidence_summary"), dict) else None
        self._hydrate_metadata_status(metadata=metadata, raw_payload=raw_payload, stats=stats)
        return self

    def _hydrate_phase22d_normalized_fields(self, *, metadata: dict[str, Any], raw_payload: dict[str, Any], stats: dict[str, Any]) -> None:
        duration = normalize_douyin_duration(raw_text=self.duration_text_raw or self.duration_text, seconds=self.duration_seconds)
        self.duration_text_raw = duration.duration_text_raw
        self.duration_text = duration.duration_text
        self.duration_seconds = duration.duration_seconds
        self.duration_parse_confidence = duration.duration_parse_confidence

        posted = normalize_douyin_posted(
            posted_at=self.posted_at,
            posted_text=self.posted_text,
            posted_text_raw=self.posted_text_raw,
            posted_display=self.posted_display,
            posted_source=self.posted_source,
        )
        self.posted_at = posted.posted_at
        self.posted_text_raw = posted.posted_text_raw
        self.posted_display = posted.posted_display
        self.posted_text = posted.posted_text
        self.posted_source = posted.posted_source
        self.posted_parse_confidence = posted.posted_parse_confidence

        estimated_views = normalize_douyin_estimated_views(
            _string_metadata(metadata, raw_payload, key="estimated_views_text_raw"),
            _string_metadata(metadata, raw_payload, key="estimated_views_display"),
            _string_metadata(metadata, raw_payload, key="estimated_views_text"),
            _string_metadata(metadata, raw_payload, key="estimated_views"),
            self.view_count_text,
            self.view_count,
        )
        self.estimated_views_text_raw = estimated_views.estimated_views_text_raw
        self.estimated_views_display = estimated_views.estimated_views_display
        self.estimated_views_min = estimated_views.estimated_views_min
        self.estimated_views_max = estimated_views.estimated_views_max
        self.estimated_views_mid = estimated_views.estimated_views_mid
        self.estimated_views_parse_confidence = estimated_views.estimated_views_parse_confidence

        if self.like_count is None:
            self.like_count = normalize_douyin_count(self.like_count_text)
        if self.comment_count is None:
            self.comment_count = normalize_douyin_count(self.comment_count_text)
        if self.comment_count is None:
            self.comment_count = normalize_douyin_engagement_count("comment", None, self.comment_count_text)
        if self.share_count is None:
            self.share_count = normalize_douyin_count(self.share_count_text)
        if self.share_count is None:
            share_source = _string_metadata(metadata, raw_payload, key="share_count_source")
            self.share_count = normalize_douyin_engagement_count(
                "share",
                None,
                self.share_count_text,
                share_icon_context=share_source == "dom_zero_sentinel" or _string_or_none(self.share_count_text) == "分享",
            )
        if self.favorite_count is None:
            self.favorite_count = normalize_douyin_count(self.favorite_count_text)
        self.follower_count = _int_metadata(metadata, raw_payload, {}, key="follower_count")
        self.follower_count_text = _string_metadata(metadata, raw_payload, key="follower_count_text")

        engagement = calculate_engagement(
            like_count=self.like_count,
            comment_count=self.comment_count,
            share_count=self.share_count,
            favorite_count=self.favorite_count,
            estimated_views_mid=self.estimated_views_mid,
            view_count=self.view_count,
        )
        self.engagement_score = engagement.engagement_score
        self.engagement_rate = engagement.engagement_rate
        self.engagement_rate_basis = engagement.engagement_rate_basis

        flags = build_data_quality_flags(
            thumbnail_url=self.thumbnail_url,
            preview_url=self.preview_url,
            posted_at=self.posted_at,
            posted_text=self.posted_text,
            duration_seconds=self.duration_seconds,
            duration_text=self.duration_text,
            estimated_views_mid=self.estimated_views_mid,
            view_count=self.view_count,
            view_count_text=self.view_count_text,
            like_count=self.like_count,
            like_count_text=self.like_count_text,
            comment_count=self.comment_count,
            comment_count_text=self.comment_count_text,
            share_count=self.share_count,
            share_count_text=self.share_count_text,
        )
        self.has_thumbnail = flags.has_thumbnail
        self.has_posted = flags.has_posted
        self.has_duration = flags.has_duration
        self.has_views = flags.has_views
        self.has_likes = flags.has_likes
        self.has_comments = flags.has_comments
        self.has_shares = flags.has_shares
        self.has_all_core_metadata = flags.has_all_core_metadata
        self.missing_metadata_fields = flags.missing_metadata_fields

    def _hydrate_metadata_status(self, *, metadata: dict[str, Any], raw_payload: dict[str, Any], stats: dict[str, Any]) -> None:
        hard_error = self.status == CapturedItemStatus.FAILED or bool(self.error_code or self.error_message or _string_metadata(metadata, raw_payload, key="metadata_hydration_error"))
        attempted = _metadata_hydration_attempted(metadata, raw_payload)
        time_captured = self.posted_at is not None or bool(_reliable_posted_text(self.posted_text))
        performance_captured = self.view_count is not None or self.like_count is not None
        processing_fit_captured = self.duration_seconds is not None
        thumbnail_captured = bool(self.thumbnail_url or self.preview_url)

        if hard_error:
            self.time_status = "failed" if not time_captured else "captured"
            self.performance_status = "failed" if not performance_captured else "captured"
            self.processing_fit_status = "failed" if not processing_fit_captured else "captured"
            self.metadata_status = "failed"
        else:
            self.time_status = "captured" if time_captured else ("missing" if attempted else "pending")
            self.performance_status = "captured" if performance_captured else ("missing" if attempted else "pending")
            self.processing_fit_status = "captured" if processing_fit_captured else ("missing" if attempted else "pending")
            captured_count = sum(status == "captured" for status in (self.time_status, self.performance_status, self.processing_fit_status))
            if captured_count == 3 and thumbnail_captured and self.has_all_core_metadata:
                self.metadata_status = "complete"
            elif captured_count > 0:
                self.metadata_status = "partial"
            elif attempted:
                self.metadata_status = "missing"
            else:
                self.metadata_status = "pending_hydration"

        self.time_missing_reason = None if time_captured else _metadata_missing_reason(self.time_status, "No posted_at or reliable posted_text captured.")
        self.performance_missing_reason = None if performance_captured else _metadata_missing_reason(self.performance_status, "No view_count or like_count captured.")
        self.processing_fit_missing_reason = None if processing_fit_captured else _metadata_missing_reason(self.processing_fit_status, "No duration_seconds captured.")
        thumbnail_missing_reason = None if thumbnail_captured else "No thumbnail_url captured."
        self.metadata_missing_reason = _overall_metadata_missing_reason(
            self.metadata_status,
            self.time_missing_reason,
            self.performance_missing_reason,
            self.processing_fit_missing_reason,
            thumbnail_missing_reason,
        )
        self.metadata_source_summary = _metadata_source_summary(self, metadata=metadata, raw_payload=raw_payload, stats=stats)
        self.last_metadata_hydrated_at = _datetime_metadata(
            metadata,
            raw_payload,
            key="last_metadata_hydrated_at",
            alternate_key="metadata_hydrated_at",
        )


class CaptureSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    capture_id: str | None = None
    source_platform: SourcePlatformEnum
    capture_source: str
    status: CaptureSessionStatus
    detected_page_type: str | None = None
    page_url: str | None = None
    page_title: str | None = None
    submitted_profile_url: str | None = None
    normalized_profile_identifier: str | None = None
    visible_item_count: int = 0
    captured_item_count: int = 0
    captured_count: int = 0
    normalized_item_count: int = 0
    duplicate_item_count: int = 0
    duplicate_count: int = 0
    ready_item_count: int = 0
    ready_count: int = 0
    needs_action_count: int = 0
    skipped_item_count: int = 0
    promoted_item_count: int = 0
    candidate_created_count: int = 0
    failed_item_count: int = 0
    failed_count: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    diagnostics_json: dict[str, Any] | None = None
    metadata_json: dict[str, Any] | None = None
    raw_summary_json: dict[str, Any] | None = None
    result_summary_json: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def hydrate_session_summary_fields(self) -> "CaptureSessionResponse":
        self.needs_action_count = max(0, self.captured_item_count - self.ready_item_count - self.duplicate_item_count - self.skipped_item_count - self.failed_item_count)
        self.captured_count = self.captured_item_count
        self.ready_count = self.ready_item_count
        self.duplicate_count = self.duplicate_item_count
        self.failed_count = self.failed_item_count
        return self


class CaptureSessionDetailResponse(CaptureSessionResponse):
    items: list[CapturedItemResponse] = Field(default_factory=list)
    reconciliation: CaptureInboxReconciliationResponse


class CaptureSessionListResponse(BaseModel):
    sessions: list[CaptureSessionResponse]
    total_count: int


class CapturedItemListResponse(BaseModel):
    items: list[CapturedItemResponse]
    total_count: int
    status_counts: dict[str, int] = Field(default_factory=dict)


class CaptureSessionCountsResponse(BaseModel):
    captured: int = 0
    ready: int = 0
    needs_action: int = 0
    dup: int = 0
    fail: int = 0


class CaptureSessionItemsBySessionResponse(BaseModel):
    session_id: UUID
    items_count: int
    items: list[CapturedItemResponse]
    counts: CaptureSessionCountsResponse


class CaptureInboxProfileItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    capture_inbox_item_id: UUID | None = None
    found: bool = True
    capture_session_id: UUID
    status: CapturedItemStatus
    source_profile_external_id: str | None = None
    profile_url: str | None = None
    normalized_profile_url: str | None = None
    source_video_external_id: str | None = None
    video_external_id: str | None = None
    external_id: str | None = None
    aweme_id: str | None = None
    metadata_status: str | None = None
    review_status: str | None = None
    title: str | None = None
    caption: str | None = None
    duration_seconds: float | None = None
    like_count: int | None = None
    comment_count: int | None = None
    favorite_count: int | None = None
    share_count: int | None = None
    posted_at: datetime | None = None
    thumbnail_url: str | None = None
    estimated_views: int | None = None
    estimated_views_formula: str | None = None
    view_count: int | None = None
    real_view_count_data_quality: str | None = None
    finalized_metadata_source: str | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def hydrate_safe_aliases(self) -> "CaptureInboxProfileItemResponse":
        self.capture_inbox_item_id = self.capture_inbox_item_id or self.id
        self.aweme_id = self.aweme_id or self.source_video_external_id
        self.video_external_id = self.video_external_id or self.source_video_external_id
        self.external_id = self.external_id or self.source_video_external_id
        return self


class CaptureInboxProfileItemsResponse(BaseModel):
    profile_identifier: str
    normalized_profile_url: str
    profile_scope: Literal["same_profile_only"] = "same_profile_only"
    source: Literal["capture_inbox_profile_items"] = "capture_inbox_profile_items"
    total_count: int
    unique_video_count: int
    offset: int = 0
    items_count: int
    counts: CaptureSessionCountsResponse
    items: list[CaptureInboxProfileItemResponse]


class CaptureInboxProfileSummaryResponse(BaseModel):
    profile_identifier: str
    normalized_profile_url: str
    profile_scope: Literal["same_profile_only"] = "same_profile_only"
    source: Literal["capture_inbox_profile_summary"] = "capture_inbox_profile_summary"
    total_count: int
    unique_video_count: int
    counts: CaptureSessionCountsResponse


class CaptureInboxItemsVerifyRequest(BaseModel):
    aweme_ids: list[str] = Field(default_factory=list)
    source_video_external_ids: list[str] = Field(default_factory=list)
    capture_session_id: UUID | None = None
    profile_url: str | None = None
    limit: int = Field(default=100, ge=1, le=500)


class CaptureInboxItemsVerifyResponse(BaseModel):
    source: Literal["capture_inbox_items_verify"] = "capture_inbox_items_verify"
    read_only: bool = True
    requested_count: int
    found_count: int
    missing_count: int
    items: list[CaptureInboxProfileItemResponse]


class CaptureSessionDebugEventResponse(BaseModel):
    time: str | None = None
    aweme_id: str | None = None
    stage: str | None = None
    status: str | None = None
    item_created_or_updated: bool | None = None
    capture_inbox_item_id: str | None = None
    error_code: str | None = None


class CaptureSessionDebugResponse(BaseModel):
    session_id: UUID
    session_exists: bool
    session: CaptureSessionResponse | None = None
    counts: CaptureSessionCountsResponse
    items_count: int
    items_sample: list[CapturedItemResponse] = Field(default_factory=list)
    last_ingest_events: list[CaptureSessionDebugEventResponse] = Field(default_factory=list)


class CaptureInboxAdvancedFilterRequest(BaseModel):
    from_date: datetime | None = None
    to_date: datetime | None = None
    min_views: int | None = Field(default=None, ge=0)
    max_views: int | None = Field(default=None, ge=0)
    min_likes: int | None = Field(default=None, ge=0)
    max_likes: int | None = Field(default=None, ge=0)
    min_comments: int | None = Field(default=None, ge=0)
    max_comments: int | None = Field(default=None, ge=0)
    min_shares: int | None = Field(default=None, ge=0)
    max_shares: int | None = Field(default=None, ge=0)
    min_engagement_rate: float | None = Field(default=None, ge=0, le=1)
    max_engagement_rate: float | None = Field(default=None, ge=0, le=1)
    min_duration_seconds: float | None = Field(default=None, ge=0)
    max_duration_seconds: float | None = Field(default=None, ge=0)
    speech: bool | None = None
    max_text_density: Literal["low", "medium", "high"] | None = None
    exclude_heavy_watermark: bool = True
    exclude_high_complexity: bool = True
    exclude_high_processing_complexity: bool = True
    exclude_high_copyright_risk: bool = True

    @model_validator(mode="after")
    def validate_ranges(self) -> "CaptureInboxAdvancedFilterRequest":
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must be before or equal to to_date")
        for lo, hi, name in (
            (self.min_views, self.max_views, "views"),
            (self.min_likes, self.max_likes, "likes"),
            (self.min_comments, self.max_comments, "comments"),
            (self.min_shares, self.max_shares, "shares"),
            (self.min_engagement_rate, self.max_engagement_rate, "engagement_rate"),
            (self.min_duration_seconds, self.max_duration_seconds, "duration_seconds"),
        ):
            if lo is not None and hi is not None and lo > hi:
                raise ValueError(f"min_{name} must be less than or equal to max_{name}")
        return self


class CaptureInboxItemQueryRequest(BaseModel):
    capture_session_id: UUID
    status: CapturedItemStatus | None = None
    studio_status: CaptureInboxStudioStatus | None = None
    search: str | None = None
    limit: int = Field(default=100, ge=1, le=500)
    offset: int = Field(default=0, ge=0)
    advanced_filter: CaptureInboxAdvancedFilterRequest | None = None


class CaptureInboxActionRequest(BaseModel):
    action: Literal["retry_enrich", "retry_preview", "promote_now", "exclude", "delete_items", "open_source", "view_raw_details", "re_evaluate_intake"]
    item_ids: list[UUID] = Field(default_factory=list, max_length=500)
    preset_name: str | None = None
    persist: bool = True
    exclude_reason: str | None = Field(default=None, max_length=500)


def _metadata_hydration_attempted(metadata: dict[str, Any], raw_payload: dict[str, Any]) -> bool:
    explicit_status = _string_metadata(metadata, raw_payload, key="metadata_status")
    if explicit_status in {"complete", "partial", "missing", "failed"}:
        return True
    if _string_metadata(metadata, raw_payload, key="last_metadata_hydrated_at") or _string_metadata(metadata, raw_payload, key="metadata_hydrated_at"):
        return True
    if _string_metadata(metadata, raw_payload, key="metadata_hydration_error"):
        return True
    attempted_keys = {
        "capture_id",
        "schema_version",
        "duration_seconds",
        "posted_at",
        "posted_text",
        "view_count",
        "like_count",
        "comment_count",
        "share_count",
        "network_source",
        "duration_source",
        "posted_source",
        "view_count_source",
        "like_count_source",
    }
    return any(key in metadata or key in raw_payload for key in attempted_keys)



def _reliable_posted_text(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    if not normalized or normalized in {"not captured", "unknown", "n/a", "none", "null"}:
        return None
    return value.strip()



def _lazy_normalize_legacy_posted(
    *,
    posted_at: datetime | None,
    posted_text: str | None,
    posted_text_raw: str | None,
    posted_display: str | None,
    reference_time: datetime | None,
) -> dict[str, Any]:
    reliable_posted_text = _reliable_posted_text(posted_text)
    reliable_posted_raw = _reliable_posted_text(posted_text_raw)
    normalized_raw = reliable_posted_raw or reliable_posted_text
    normalized_posted_at = posted_at
    normalized_display = _normalize_posted_display(posted_display)

    if normalized_posted_at is not None and normalized_display is None:
        normalized_display = _format_posted_display(normalized_posted_at)

    if normalized_posted_at is None and normalized_display is None and normalized_raw:
        parsed_posted_at = _parse_douyin_posted(normalized_raw, reference_time=reference_time)
        if parsed_posted_at is not None:
            normalized_posted_at = parsed_posted_at
            normalized_display = _format_posted_display(parsed_posted_at)

    normalized_posted_text = normalized_display or reliable_posted_text or normalized_raw
    return {
        "posted_at": normalized_posted_at,
        "posted_text_raw": normalized_raw,
        "posted_display": normalized_display,
        "posted_text": normalized_posted_text,
    }



def _normalize_posted_display(value: str | None) -> str | None:
    reliable = _reliable_posted_text(value)
    if not reliable:
        return None
    normalized = reliable.strip()
    return normalized if _is_dd_mm_yyyy(normalized) else None



def _is_dd_mm_yyyy(value: str) -> bool:
    parts = value.split("/")
    if len(parts) != 3:
        return False
    day, month, year = parts
    if len(day) != 2 or len(month) != 2 or len(year) != 4:
        return False
    if not (day.isdigit() and month.isdigit() and year.isdigit()):
        return False
    day_value = int(day)
    month_value = int(month)
    year_value = int(year)
    return 1 <= day_value <= 31 and 1 <= month_value <= 12 and year_value >= 1900



def _format_posted_display(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value.astimezone(UTC)
    shifted = normalized + timedelta(hours=8)
    return shifted.strftime("%d/%m/%Y")



def _parse_douyin_posted(value: str, *, reference_time: datetime | None) -> datetime | None:
    normalized = _normalize_douyin_posted_raw(value)
    if not normalized:
        return None

    reference = reference_time or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    else:
        reference = reference.astimezone(UTC)

    candidate = _posted_candidate(normalized)
    if not candidate:
        return None

    absolute_match = re.match(r"^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})(?:日)?(?:\s+(\d{1,2}):(\d{2}))?$", candidate)
    if absolute_match:
        return _safe_datetime(
            int(absolute_match.group(1)),
            int(absolute_match.group(2)),
            int(absolute_match.group(3)),
            int(absolute_match.group(4) or 0),
            int(absolute_match.group(5) or 0),
        )

    month_day_match = re.match(r"^(\d{1,2})月(\d{1,2})日(?:\s+(\d{1,2}):(\d{2}))?$", candidate)
    if month_day_match:
        parsed = _safe_datetime(
            reference.year,
            int(month_day_match.group(1)),
            int(month_day_match.group(2)),
            int(month_day_match.group(3) or 0),
            int(month_day_match.group(4) or 0),
        )
        if parsed and parsed - reference > timedelta(days=7):
            parsed = _safe_datetime(
                reference.year - 1,
                int(month_day_match.group(1)),
                int(month_day_match.group(2)),
                int(month_day_match.group(3) or 0),
                int(month_day_match.group(4) or 0),
            )
        return parsed

    english_absolute = _parse_english_posted(candidate, reference=reference)
    if english_absolute is not None:
        return english_absolute

    if candidate == "刚刚" or candidate.lower() == "just now":
        return reference
    if candidate == "昨天" or candidate.lower() == "yesterday":
        return reference - timedelta(days=1)
    if candidate == "前天":
        return reference - timedelta(days=2)

    relative_match = re.match(r"^(\d+|一|两)\s*(秒|分钟|小时|天|周|星期|个月|月|年)前$", candidate)
    if relative_match:
        amount_token = relative_match.group(1)
        amount = int(amount_token) if amount_token.isdigit() else (1 if amount_token == "一" else 2 if amount_token == "两" else -1)
        if amount < 0:
            return None
        unit = relative_match.group(2)
        if unit == "秒":
            return reference - timedelta(seconds=amount)
        if unit == "分钟":
            return reference - timedelta(minutes=amount)
        if unit == "小时":
            return reference - timedelta(hours=amount)
        if unit == "天":
            return reference - timedelta(days=amount)
        if unit in {"周", "星期"}:
            return reference - timedelta(days=amount * 7)
        if unit in {"个月", "月"}:
            return _add_calendar_months(reference, -amount)
        if unit == "年":
            return _add_calendar_months(reference, -(amount * 12))

    english_relative = re.match(r"^(\d+)\s*(second|minute|hour|day|week|month|year)s?\s+ago$", candidate, flags=re.IGNORECASE)
    if english_relative:
        amount = int(english_relative.group(1))
        unit = english_relative.group(2).lower()
        if unit == "second":
            return reference - timedelta(seconds=amount)
        if unit == "minute":
            return reference - timedelta(minutes=amount)
        if unit == "hour":
            return reference - timedelta(hours=amount)
        if unit == "day":
            return reference - timedelta(days=amount)
        if unit == "week":
            return reference - timedelta(days=amount * 7)
        if unit == "month":
            return _add_calendar_months(reference, -amount)
        if unit == "year":
            return _add_calendar_months(reference, -(amount * 12))
    return None


def _normalize_douyin_posted_raw(value: str) -> str | None:
    normalized = re.sub(r"\s+", " ", value.strip())
    normalized = re.sub(r"^[·•・。\s]+", "", normalized).strip()
    label = re.match(r"^(?:发布时间|发布于|发布时间为)\s*[:：]?\s*(.+)$", normalized, flags=re.IGNORECASE)
    if label:
        normalized = label.group(1).strip()
    author = re.match(r"^@?[^·•・。\n]{1,80}\s*[·•・。]\s*(.+)$", normalized)
    if author and _posted_candidate(author.group(1)):
        normalized = author.group(1).strip()
    normalized = re.sub(r"^[·•・。\s]+", "", normalized).strip()
    return normalized or None


def _posted_candidate(value: str) -> str | None:
    text = re.sub(r"\s+", " ", value.strip())
    patterns = (
        r"(?:发布时间|发布于|发布时间为)\s*[:：]?\s*(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)",
        r"(\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}(?:日)?(?:\s+\d{1,2}:\d{2})?)",
        r"(\d{1,2}月\d{1,2}日(?:\s+\d{1,2}:\d{2})?)",
        r"(((?:\d+|一|两)\s*(?:秒|分钟|小时|天|周|星期|个月|月|年))前|刚刚|昨天|前天)",
        r"((?:just now|yesterday|\d+\s*(?:second|minute|hour|day|week|month|year)s?\s+ago))",
        r"([A-Za-z]{3,9}\s+\d{1,2}(?:,\s*\d{4})?)",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _parse_english_posted(value: str, *, reference: datetime) -> datetime | None:
    match = re.match(r"^([A-Za-z]{3,9})\s+(\d{1,2})(?:,\s*(\d{4}))?$", value)
    if not match:
        return None
    month_names = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
    month = next((index + 1 for index, name in enumerate(month_names) if match.group(1).lower().startswith(name)), None)
    if month is None:
        return None
    year = int(match.group(3)) if match.group(3) else reference.year
    parsed = _safe_datetime(year, month, int(match.group(2)), 0, 0)
    if not match.group(3) and parsed and parsed - reference > timedelta(days=7):
        parsed = _safe_datetime(year - 1, month, int(match.group(2)), 0, 0)
    return parsed


def _safe_datetime(year: int, month: int, day: int, hour: int, minute: int) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, tzinfo=UTC)
    except ValueError:
        return None


def _add_calendar_months(value: datetime, months_delta: int) -> datetime:
    month_index = value.year * 12 + (value.month - 1) + months_delta
    year = month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)



def _metadata_missing_reason(status: MetadataGroupStatus, missing_message: str) -> str:
    if status == "pending":
        return "Metadata hydration has not been attempted."
    if status == "failed":
        return "Metadata hydration failed before this evidence was captured."
    return missing_message



def _overall_metadata_missing_reason(metadata_status: MetadataStatus, *group_reasons: str | None) -> str | None:
    reasons = [reason for reason in group_reasons if reason]
    if metadata_status == "complete":
        return None
    if metadata_status == "pending_hydration":
        return "Metadata hydration has not been attempted."
    if metadata_status == "failed":
        return "Metadata hydration failed."
    return "; ".join(reasons) if reasons else None



def _metadata_source_summary(response: CapturedItemResponse, *, metadata: dict[str, Any], raw_payload: dict[str, Any], stats: dict[str, Any]) -> str:
    explicit = _string_metadata(metadata, raw_payload, key="metadata_source_summary")
    if explicit:
        return explicit
    entries: list[str] = []
    if response.posted_source:
        entries.append(f"time:{response.posted_source}")
    elif response.posted_at is not None or response.posted_text:
        entries.append("time:canonical")
    if response.view_count_source or response.like_count_source:
        sources = sorted({source for source in (response.view_count_source, response.like_count_source, response.comment_count_source, response.share_count_source) if source})
        entries.append(f"performance:{'+'.join(sources)}")
    elif response.view_count is not None or response.like_count is not None or stats:
        entries.append("performance:canonical")
    if response.duration_source:
        entries.append(f"processing_fit:{response.duration_source}")
    elif response.duration_seconds is not None:
        entries.append("processing_fit:canonical")
    network_source = _string_metadata(metadata, raw_payload, key="network_source")
    if network_source:
        entries.append(f"network:{network_source}")
    return "; ".join(entries) if entries else "No metadata source evidence captured."



def _datetime_metadata(*payloads: dict[str, Any], key: str, alternate_key: str | None = None) -> datetime | None:
    for payload in payloads:
        for candidate_key in (key, alternate_key):
            if not candidate_key:
                continue
            value = payload.get(candidate_key)
            if isinstance(value, datetime):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
                except ValueError:
                    continue
    return None



def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _nested_payload(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    return value if isinstance(value, dict) else {}


def _capture_item_title_from_payloads(
    *,
    caption: str | None,
    metadata: dict[str, Any],
    raw_payload: dict[str, Any],
    aweme_id: str | None,
) -> str | None:
    blocked = {value for value in (_string_or_none(aweme_id),) if value}
    metadata_evidence = _nested_payload(metadata, "profile_card_evidence")
    metadata_dom = _nested_payload(metadata, "raw_dom_detail_metrics")
    raw_evidence = _nested_payload(raw_payload, "profile_card_evidence")
    raw_dom = _nested_payload(raw_payload, "raw_dom_detail_metrics")
    for value in (
        caption,
        raw_payload.get("title"),
        raw_payload.get("desc"),
        metadata.get("title"),
        metadata_evidence.get("title"),
        metadata_evidence.get("caption"),
        metadata_evidence.get("desc"),
        metadata_evidence.get("description"),
        metadata_dom.get("title"),
        raw_evidence.get("title"),
        raw_evidence.get("caption"),
        raw_evidence.get("desc"),
        raw_evidence.get("description"),
        raw_dom.get("title"),
    ):
        title = _string_or_none(value)
        if title and title not in blocked:
            return title
    return None


def _string_metadata(*payloads: dict[str, Any], key: str) -> str | None:
    for payload in payloads:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None



def _int_metadata(*payloads: dict[str, Any], key: str, alternate_key: str | None = None) -> int | None:
    for payload in payloads:
        for candidate_key in (key, alternate_key):
            if not candidate_key:
                continue
            value = payload.get(candidate_key)
            if value is None or value == "":
                continue
            try:
                return int(float(value))
            except (TypeError, ValueError):
                continue
    return None


def _bool_metadata(*payloads: dict[str, Any], key: str) -> bool | None:
    for payload in payloads:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized == "true":
                return True
            if normalized == "false":
                return False
    return None


def _float_metadata(*payloads: dict[str, Any], key: str) -> float | None:
    for payload in payloads:
        value = payload.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str) and value.strip():
            try:
                return float(value)
            except ValueError:
                continue
    return None


class CaptureInboxActionItemResult(BaseModel):
    item_id: UUID
    reason: str


class CaptureInboxActionResponse(BaseModel):
    success: bool = True
    action: str
    capture_session_id: UUID | None = None
    affected_item_ids: list[UUID] = Field(default_factory=list)
    promoted_item_count: int = 0
    candidate_created_count: int = 0
    candidate_updated_count: int = 0
    message: str
    session: CaptureSessionResponse | None = None
    items: list[CapturedItemResponse] = Field(default_factory=list)
    skipped: list[CaptureInboxActionItemResult] = Field(default_factory=list)
    failed: list[CaptureInboxActionItemResult] = Field(default_factory=list)
    raw_details: list[dict[str, Any]] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
