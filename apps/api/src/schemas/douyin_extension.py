from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

DouyinThumbnailSource = Literal["network_json", "dom_fallback", "detail_hydrate", "missing"]
DouyinThumbnailMissingReason = Literal[
    "network_cover_missing",
    "detail_hydrate_not_run",
    "detail_hydrate_no_cover",
    "dom_cover_missing",
    "backend_drop",
    "api_drop",
    "frontend_resolver_drop",
    "thumbnail_unresolved",
]

DouyinExtensionSetupStatus = Literal[
    "not_installed_or_not_connected",
    "installed_not_connected",
    "connected",
    "version_mismatch",
    "backend_unreachable_from_extension",
    "stale_connection",
]
DouyinExtensionBrowserFamily = Literal["chrome", "edge", "chromium", "unknown"]
DouyinExtensionVersionStatus = Literal["compatible", "version_mismatch", "unknown"]
DouyinExtensionRecommendedAction = Literal[
    "download_extension",
    "build_extension",
    "install_extension_manually",
    "open_extension_and_check_connection",
    "refresh_setup_page",
    "update_extension",
    "open_douyin_and_capture",
    "detect_current_page",
    "capture_current_page",
    "check_backend_url",
]
DouyinExtensionManagerEventType = Literal["handshake", "detect", "capture"]
DouyinExtensionManagerEventStatus = Literal["success", "failed"]
DouyinPreviewStatus = Literal["ready", "pending", "missing"]
DouyinSourceLinkStatus = Literal["captured", "missing"]
DouyinMediaAssetStatus = Literal["not_generated", "ready", "failed"]
DouyinMediaStatus = Literal["ready", "pending", "missing", "source_link_captured"]
DouyinPostedSource = Literal["network_json", "detail_hydrate", "dom_text", "fallback_none"]
DouyinMetricSource = Literal["network_json", "detail_hydrate", "dom_fallback", "dom_text", "fallback_none"]
DouyinDurationSource = Literal["network_json", "detail_hydrate", "dom_fallback", "dom_text", "fallback_none"]
DouyinEngagementRateSource = Literal[
    "derived_from_counts",
    "derived_from_canonical_counts",
    "network_json",
    "detail_hydrate",
    "dom_detail_modal",
    "dom_fallback",
    "fallback_none",
]
DouyinTextDensity = Literal["low", "medium", "high"]
DouyinProcessingComplexity = Literal["low", "medium", "high", "blocking"]
DouyinCopyrightRisk = Literal["low", "medium", "high", "true"]
DouyinContextMismatchCode = Literal[
    "context_mismatch",
    "session_mismatch",
    "project_mismatch",
    "profile_mismatch",
    "tab_mismatch",
    "page_mismatch",
]

DouyinExtensionPageType = Literal[
    "login_page",
    "challenge_page",
    "home_feed_page",
    "profile_page",
    "profile_feed_page",
    "video_detail_page",
    "unsupported_page",
    "unknown_page",
]


class DouyinExtensionPageSnapshot(BaseModel):
    url: str | None = None
    title: str | None = None
    body_text_sample: str | None = Field(default=None, max_length=4000)
    page_type: DouyinExtensionPageType | None = None
    profile_url: str | None = None
    profile_external_id: str | None = None
    handle: str | None = None
    display_name: str | None = None
    video_link_count: int = Field(default=0, ge=0)


class DouyinExtensionDetectPageRequest(BaseModel):
    page: DouyinExtensionPageSnapshot
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DouyinExtensionDetectPageResponse(BaseModel):
    diagnostics_id: str
    detected_page_type: DouyinExtensionPageType
    supported_capture: bool
    recommended_action: str
    recommended_action_label: str
    operator_message: str
    page_url: str | None = None
    normalized_profile_url: str | None = None
    title: str | None = None
    video_link_count: int = 0
    detected_at: datetime


class DouyinExtensionProfilePayload(BaseModel):
    id: str | None = None
    sec_uid: str | None = None
    handle: str | None = None
    unique_id: str | None = None
    display_name: str | None = None
    nickname: str | None = None
    follower_count: int | None = None
    following_count: int | None = None


class DouyinExtensionCaptureContextPayload(BaseModel):
    capture_id: str | None = Field(default=None, max_length=120)
    tab_id: int | None = None
    page_url: str | None = None
    page_url_normalized: str | None = None
    profile_url: str | None = None
    profile_external_id: str | None = None
    captured_at: datetime | str | None = None
    cache_scope_key: str | None = None


class DouyinExtensionRawDomDetailMetrics(BaseModel):
    aweme_id: str | None = Field(default=None, min_length=1, max_length=180)
    target_aweme_id: str | None = Field(default=None, min_length=1, max_length=180)
    duration_seconds: float | None = None
    duration_text: str | None = None
    duration_text_conflict: str | None = None
    like_count: int | None = None
    like_count_text: str | None = None
    like_count_source: str | None = None
    comment_count: int | None = None
    comment_count_text: str | None = None
    comment_count_source: str | None = None
    favorite_count: int | None = None
    favorite_count_text: str | None = None
    share_count: int | None = None
    share_count_text: str | None = None
    share_count_source: str | None = None
    view_count: int | None = Field(default=None, ge=0)
    view_count_source: str | None = None
    posted_text: str | None = None
    posted_text_raw: str | None = None
    posted_at: datetime | str | None = None
    posted_display: str | None = None
    posted_source: str | None = None
    posted_parse_confidence: str | None = None
    selected_duration_source: str | None = None
    duration_text_source: str | None = None
    action_blocks_found: int | None = None
    modal_action_blocks_found: int | None = None
    like_block_text: str | None = None
    comment_block_text: str | None = None
    favorite_block_text: str | None = None
    share_block_text: str | None = None
    profile_card_like_text: str | None = None
    assigned_metric_node_ids: list[str] | None = None
    metric_confidence_by_field: dict[str, str] | None = None
    rejected_metric_reasons: dict[str, str] | None = None
    extraction_warning: str | None = None
    extraction_source: Literal[
        "dom_detail_modal",
        "video_element_modal",
        "calibrated_point_dom",
        "calibrated_point_ocr",
        "mixed_calibrated_point",
        "page_network_cache_aweme",
        "exact_aweme_network_cache_object",
    ]
    confidence: Literal["high"]


class DouyinExtensionRawEvidenceSummary(BaseModel):
    has_network_aweme: bool = False
    has_detail_aweme: bool = False
    has_dom_snapshot: bool = False
    has_dom_detail_metrics: bool = False
    network_keys: list[str] = Field(default_factory=list)
    detail_keys: list[str] = Field(default_factory=list)
    dom_detail_metric_keys: list[str] = Field(default_factory=list)
    evidence_sources: list[str] = Field(default_factory=list)
    evidence_collection_version: Literal[
        "phase2",
        "phase5c_detail_hydrate",
        "phase6h_full_modal_auto_harvest",
        "phase10a_calibrated_point_extractor",
        "phase10c_smart_capture_harvest",
        "phase11a_production_stabilized_calibrated_harvest",
        "phase12a_calibrated_five_point_workflow",
        "phase12c_recovered_four_point_harvest",
        "phase12d_four_point_navigation_loop_fix",
        "phase17a_finalized_only_harvest",
    ] = "phase6h_full_modal_auto_harvest"


class DouyinExtensionVideoPayload(BaseModel):
    id: str | None = None
    aweme_id: str | None = None
    video_id: str | None = None
    source_video_url: str | None = None
    share_url: str | None = None
    url: str | None = None
    title: str | None = None
    desc: str | None = None
    description: str | None = None
    duration_seconds: float | None = None
    duration: float | None = None
    duration_text: str | None = None
    posted_at: datetime | int | str | None = None
    create_time: datetime | int | str | None = None
    posted_text: str | None = None
    posted_text_raw: str | None = None
    posted_display: str | None = None
    thumbnail_url: str | None = None
    poster_url: str | None = None
    cover_url: str | None = None
    thumb_url: str | None = None
    image_url: str | None = None
    thumbnail: str | dict[str, Any] | None = None
    cover: str | dict[str, Any] | None = None
    poster: str | dict[str, Any] | None = None
    origin_cover: str | dict[str, Any] | None = None
    dynamic_cover: str | dict[str, Any] | None = None
    animated_cover: str | dict[str, Any] | None = None
    image: str | dict[str, Any] | None = None
    url_list: list[str] | None = None
    poster_aspect_ratio: float | None = None
    thumbnail_source_type: str | None = None
    thumbnail_source_types: list[str] | None = None
    thumbnail_source: DouyinThumbnailSource | None = None
    thumbnail_missing_reason: DouyinThumbnailMissingReason | None = None
    posted_source: DouyinPostedSource | None = None
    duration_source: DouyinDurationSource | None = None
    view_count_source: DouyinMetricSource | None = None
    like_count_source: DouyinMetricSource | None = None
    comment_count_source: DouyinMetricSource | None = None
    share_count_source: DouyinMetricSource | None = None
    engagement_rate_source: DouyinEngagementRateSource | None = None
    network_source: str | None = None
    raw: dict[str, Any] | None = None
    raw_network_aweme: dict[str, Any] | None = None
    raw_detail_aweme: dict[str, Any] | None = None
    raw_dom_snapshot: dict[str, Any] | None = None
    raw_dom_detail_metrics: DouyinExtensionRawDomDetailMetrics | None = None
    raw_evidence_summary: dict[str, Any] | None = None
    view_count_text: str | None = None
    view_count: int | None = None
    like_count_text: str | None = None
    like_count: int | None = None
    comment_count_text: str | None = None
    comment_count: int | None = None
    share_count: int | None = None
    engagement_rate: float | None = None
    preview_status: DouyinPreviewStatus | None = None
    source_link_status: DouyinSourceLinkStatus | None = None
    media_asset_status: DouyinMediaAssetStatus | None = None
    media_status: DouyinMediaStatus | None = None
    has_speech: bool | None = None
    text_density: DouyinTextDensity | None = None
    has_heavy_watermark: bool | None = None
    processing_complexity: DouyinProcessingComplexity | None = None
    copyright_risk: DouyinCopyrightRisk | None = None
    capture_context: DouyinExtensionCaptureContextPayload | None = None
    context_mismatch_codes: list[DouyinContextMismatchCode] = Field(default_factory=list)
    extraction_diagnostics: dict[str, Any] | None = None
    statistics: dict[str, Any] = Field(default_factory=dict)
    stats: dict[str, Any] = Field(default_factory=dict)


DouyinExtensionTargetCaptureStatus = Literal["new", "incomplete", "complete", "failed", "skipped", "unknown"]
DouyinProfileVideoClassificationStatus = Literal["new", "incomplete", "complete", "failed", "skipped", "unknown"]
DouyinProfileVideoCollectionMode = Literal["new_incomplete_failed", "new_and_incomplete", "new_only", "failed_only", "refresh_all"]


class DouyinProfileVideoCandidate(BaseModel):
    aweme_id: str
    video_url: str | None = None
    source_url: str | None = None
    thumbnail_url: str | None = None
    caption: str | None = None
    posted_text: str | None = None
    posted_at: str | None = None
    view_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def normalize_aweme_id(self) -> "DouyinProfileVideoCandidate":
        self.aweme_id = str(self.aweme_id or "").strip()
        return self


class DouyinProfileVideoClassificationRequest(BaseModel):
    schema_version: Literal["douyin_profile_video_classification.v1"] = "douyin_profile_video_classification.v1"
    profile_url: str = Field(min_length=1, max_length=2000)
    sec_uid: str | None = None
    collection_mode: DouyinProfileVideoCollectionMode = "new_incomplete_failed"
    candidates: list[DouyinProfileVideoCandidate] = Field(default_factory=list, max_length=1000)
    include_unknown: bool = False
    dry_run: bool = True


class DouyinProfileClassificationCounts(BaseModel):
    new: int = 0
    incomplete: int = 0
    complete: int = 0
    failed: int = 0
    skipped: int = 0
    unknown: int = 0
    collect: int = 0
    skip: int = 0


class DouyinProfileVideoClassificationTarget(BaseModel):
    aweme_id: str
    classification: DouyinProfileVideoClassificationStatus
    collect: bool
    reason: str
    required_missing_fields: list[str] = Field(default_factory=list)
    existing_item_id: str | None = None
    metadata_status: str | None = None
    review_status: str | None = None
    video_url: str | None = None
    source_url: str | None = None
    thumbnail_url: str | None = None
    caption: str | None = None


class DouyinProfileVideoClassificationResponse(BaseModel):
    schema_version: Literal["douyin_profile_video_classification_result.v1"] = "douyin_profile_video_classification_result.v1"
    profile_url: str
    sec_uid: str | None = None
    collection_mode: str
    database_lookup_status: str
    total_candidates: int
    counts: DouyinProfileClassificationCounts
    targets: list[DouyinProfileVideoClassificationTarget] = Field(default_factory=list)
    collect_aweme_ids: list[str] = Field(default_factory=list)
    skip_aweme_ids: list[str] = Field(default_factory=list)
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DouyinExtensionTargetClassificationTarget(BaseModel):
    aweme_id: str = Field(min_length=1, max_length=180)
    source_video_external_id: str | None = Field(default=None, min_length=1, max_length=180)
    metadata_status: str | None = Field(default=None, max_length=80)
    review_status: str | None = Field(default=None, max_length=80)
    source_url: str | None = None


class DouyinExtensionTargetClassificationRequest(BaseModel):
    schema_version: Literal["douyin_extension_target_classification.v1"] = "douyin_extension_target_classification.v1"
    profile_url: str = Field(min_length=1, max_length=2000)
    source: Literal["whole_profile_harvest"] = "whole_profile_harvest"
    targets: list[DouyinExtensionTargetClassificationTarget] = Field(default_factory=list, max_length=500)


class DouyinExtensionTargetClassificationItem(BaseModel):
    aweme_id: str
    source_video_external_id: str
    capture_status: DouyinExtensionTargetCaptureStatus
    item_id: UUID | None = None
    metadata_status: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    existing_fields: dict[str, bool] = Field(default_factory=dict)
    updated_at: datetime | None = None


class DouyinExtensionTargetClassificationResponse(BaseModel):
    ok: bool = True
    profile_url: str
    items: list[DouyinExtensionTargetClassificationItem] = Field(default_factory=list)
    counts: dict[DouyinExtensionTargetCaptureStatus, int]


class DouyinExtensionHarvestPlanProfileCardEvidence(BaseModel):
    aweme_id: str = Field(min_length=1, max_length=180)
    source_url: str | None = None
    title: str | None = None
    caption: str | None = None
    desc: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    cover_url: str | None = None
    poster_url: str | None = None
    posted_text: str | None = None
    posted_text_raw: str | None = None
    posted_at: datetime | None = None
    posted_display: str | None = None
    thumbnail_source: str | None = None
    posted_source: str | None = None
    posted_parse_confidence: str | None = None
    raw_profile_card: dict[str, Any] | None = None


class DouyinExtensionHarvestPlanRequest(BaseModel):
    schema_version: Literal["douyin_extension_harvest_plan.v1"] = "douyin_extension_harvest_plan.v1"
    capture_id: str = Field(min_length=1, max_length=120)
    captured_at: datetime
    page: DouyinExtensionPageSnapshot
    profile: DouyinExtensionProfilePayload | None = None
    capture_context: DouyinExtensionCaptureContextPayload
    videos: list[DouyinExtensionVideoPayload] = Field(default_factory=list, max_length=500)
    harvest_mode: Literal["new_and_incomplete", "new_only", "refresh_all"] = "new_and_incomplete"
    diagnostics: dict[str, Any] = Field(default_factory=dict)


class DouyinExtensionHarvestPlanResponse(BaseModel):
    success: bool = True
    diagnostics_id: str
    plan_id: str
    capture_id: str
    detected_page_type: DouyinExtensionPageType
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    harvest_mode: Literal["new_and_incomplete", "new_only", "refresh_all"] = "new_and_incomplete"
    total_found: int = 0
    new_count: int = 0
    incomplete_count: int = 0
    complete_count: int = 0
    skipped_count: int = 0
    target_count: int = 0
    target_aweme_ids: list[str] = Field(default_factory=list)
    new_aweme_ids: list[str] = Field(default_factory=list)
    incomplete_aweme_ids: list[str] = Field(default_factory=list)
    complete_aweme_ids: list[str] = Field(default_factory=list)
    skipped_aweme_ids: list[str] = Field(default_factory=list)
    profile_card_evidence_by_aweme_id: dict[str, DouyinExtensionHarvestPlanProfileCardEvidence] = Field(default_factory=dict)
    created_visible_item_count: int = 0
    stage: str = "harvest_plan_created"
    warning_codes: list[str] = Field(default_factory=list)
    discovered_at: datetime


class DouyinExtensionCaptureRequest(BaseModel):
    schema_version: str = "douyin_extension_capture.v1"
    capture_id: str | None = Field(default=None, max_length=120)
    captured_at: datetime | None = None
    workspace_id: UUID | None = None
    preset_name: str | None = None
    filter_config: dict[str, Any] | None = None
    persist: bool = True
    page: DouyinExtensionPageSnapshot
    profile: DouyinExtensionProfilePayload | None = None
    capture_context: DouyinExtensionCaptureContextPayload | None = None
    videos: list[DouyinExtensionVideoPayload] = Field(default_factory=list, max_length=500)
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    harvest_mode: Literal["new_only", "new_and_incomplete", "refresh_all"] = "new_and_incomplete"

    @model_validator(mode="after")
    def validate_thresholds(self) -> "DouyinExtensionCaptureRequest":
        if self.filter_config is None:
            return self
        min_duration = self.filter_config.get("min_duration_seconds")
        max_duration = self.filter_config.get("max_duration_seconds")
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            raise ValueError("min_duration_seconds cannot be greater than max_duration_seconds")
        return self


class DouyinExtensionCaptureFailureSummaryResponse(BaseModel):
    stage: str
    item_index: int | None = None
    code: str
    message: str


class DouyinExtensionCaptureResponse(BaseModel):
    success: bool = True
    diagnostics_id: str
    capture_id: str | None = None
    detected_page_type: DouyinExtensionPageType
    capture_session_id: UUID | None = None
    source_profile_id: UUID | None = None
    crawl_session_id: UUID | None
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    videos_discovered_count: int = 0
    videos_created_count: int = 0
    videos_updated_count: int = 0
    candidates_total_count: int = 0
    candidates_matched_count: int = 0
    candidates_rejected_count: int = 0
    candidate_results_count: int = 0
    captured_item_count: int = 0
    normalized_item_count: int = 0
    duplicate_item_count: int = 0
    ready_item_count: int = 0
    skipped_item_count: int = 0
    promoted_item_count: int = 0
    candidate_created_count: int = 0
    failed_item_count: int = 0
    stage: str = "capture_session_staged"
    error_code: str | None = None
    warning_codes: list[str] = Field(default_factory=list)
    failure_summaries: list[DouyinExtensionCaptureFailureSummaryResponse] = Field(default_factory=list)
    visible_captured_count: int = 0
    submitted_count: int = 0
    staged_count: int = 0
    deduped_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    filters_applied_summary: dict[str, Any] = Field(default_factory=dict)
    unsupported_filters_ignored: list[str] = Field(default_factory=list)
    fetch_mode: str = "extension_current_tab_capture"
    fetch_stage: str | None = None
    fetch_stage_code: str | None = None
    fetch_stage_message: str | None = None
    parser_strategy: str | None = None
    fetch_execution_path: str | None = None
    fallback_from_execution_path: str | None = None
    strategy_policy: str | None = None
    primary_execution_path: str | None = None
    http_fallback_attempted: bool | None = None
    http_fallback_reason: str | None = None
    preflight_ran: bool = False
    videos_normalized_count: int = 0
    videos_persisted_count: int = 0
    next_suggested_route: str = "/ops/extensions/douyin/capture-inbox"
    warning: str | None = None
    discovered_at: datetime
    current_page_url: str | None = None
    current_page_title: str | None = None
    current_page_video_link_count: int = 0
    targeted_aweme_one_shot_summary: dict[str, Any] = Field(default_factory=lambda: {"items": []})
    scan_summary: dict[str, Any] = Field(default_factory=dict)
    total_found: int = 0
    new_count: int = 0
    incomplete_count: int = 0
    complete_count: int = 0
    target_aweme_ids: list[str] = Field(default_factory=list)
    new_aweme_ids: list[str] = Field(default_factory=list)
    incomplete_aweme_ids: list[str] = Field(default_factory=list)
    complete_aweme_ids: list[str] = Field(default_factory=list)


class DouyinExtensionFullModalHarvestItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    aweme_id: str = Field(min_length=1, max_length=180)
    source_video_external_id: str | None = Field(default=None, min_length=1, max_length=180)
    metadata_status: str | None = Field(default=None, max_length=80)
    review_status: str | None = Field(default=None, max_length=80)
    source_url: str | None = None
    page_url: str | None = None
    modal_id: str | None = Field(default=None, min_length=1, max_length=180)
    target_aweme_id: str | None = Field(default=None, min_length=1, max_length=180)
    modal_aweme_id_before_extract: str | None = Field(default=None, min_length=1, max_length=180)
    modal_aweme_id_after_extract: str | None = Field(default=None, min_length=1, max_length=180)
    extracted_aweme_id: str | None = Field(default=None, min_length=1, max_length=180)
    data_integrity_status: Literal["ok", "mismatch", "pending", "passed", "failed"] | None = None
    data_integrity_reason: str | None = None
    metric_signature: str | None = None
    duplicate_signature_warning: str | None = None
    view_count: int | None = Field(default=None, ge=0)
    real_view_count_available: bool | None = None
    real_view_count_data_quality: str | None = None
    estimated_views: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    estimated_views_formula: str | None = None
    estimated_views_used: bool | None = None
    real_view_count_overwritten: bool | None = None
    finalized_metadata_source: Literal["modal_detail_extraction", "guarded_hybrid_network_cache"] | None = None
    raw_dom_detail_metrics: DouyinExtensionRawDomDetailMetrics
    raw_detail_aweme: dict[str, Any] | None = None
    raw_evidence_summary: DouyinExtensionRawEvidenceSummary
    profile_card_evidence: DouyinExtensionHarvestPlanProfileCardEvidence | None = None

    @model_validator(mode="after")
    def validate_estimated_views_and_view_count_policy(self) -> "DouyinExtensionFullModalHarvestItemPayload":
        if self.estimated_views is not None and self.estimated_views_formula != "tiered_like_multiplier_v1":
            raise ValueError("estimated_views_formula must be tiered_like_multiplier_v1 when estimated_views is present")
        if self.real_view_count_overwritten is True:
            raise ValueError("real_view_count_overwritten must be false for production full modal harvest")
        if self.estimated_views is not None and self.view_count is not None and float(self.view_count) == float(self.estimated_views):
            raise ValueError("estimated_views must not be copied into view_count")
        if self.view_count is None and "view_count" in self.model_fields_set:
            quality = (self.real_view_count_data_quality or "").strip()
            if self.real_view_count_available is not False and quality not in {"trusted_zero_only_low_confidence", "real_view_count_null_low_confidence_or_missing"}:
                raise ValueError("view_count may be null only when real view count is unavailable, low confidence, or missing")
        if self.real_view_count_data_quality == "trusted_zero_only_low_confidence" and self.view_count == 0:
            raise ValueError("low-confidence zero view_count must be sent as null, not real zero")
        return self


class DouyinExtensionFullModalHarvestProgress(BaseModel):
    running: bool
    target_count: int = Field(ge=0)
    current_aweme_id: str | None = None
    harvested_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    failed_count: int = Field(ge=0)
    flushed_count: int = Field(ge=0)
    last_error: str | None = None
    stopped_reason: str | None = None


DouyinExtensionCaptureSessionSource = Literal["whole_profile_harvest", "whole_profile_staged_harvest_v2"]


class DouyinExtensionCaptureSessionRequest(BaseModel):
    schema_version: Literal["douyin_extension_capture_session.v1"] = "douyin_extension_capture_session.v1"
    source: DouyinExtensionCaptureSessionSource
    profile_url: str = Field(min_length=1, max_length=1000)
    normalized_profile_url: str | None = Field(default=None, min_length=1, max_length=1000)
    profile_sec_uid_or_path: str | None = Field(default=None, max_length=300)
    profile_display_name: str | None = Field(default=None, max_length=300)
    profile_avatar_url: str | None = Field(default=None, max_length=2000)
    display_title: str | None = Field(default=None, max_length=300)
    source_modal_aweme_id: str | None = Field(default=None, max_length=180)
    verified_target_count: int = Field(default=0, ge=0)
    queued_count: int = Field(default=0, ge=0)
    run_id: str = Field(min_length=1, max_length=180)
    mode: DouyinExtensionCaptureSessionSource

    @model_validator(mode="after")
    def validate_source_mode_match(self) -> "DouyinExtensionCaptureSessionRequest":
        if self.mode != self.source:
            raise ValueError("capture session source and mode must match")
        return self


class DouyinExtensionCaptureSessionResponse(BaseModel):
    ok: bool = True
    session_id: UUID
    created: bool
    profile_url: str
    source: str
    run_id: str


class DouyinExtensionFullModalHarvestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["douyin_full_modal_harvest.v1"] = "douyin_full_modal_harvest.v1"
    capture_session_id: UUID | None = None
    capture_session_source: str | None = Field(default=None, max_length=120)
    run_id: str | None = Field(default=None, max_length=180)
    profile_url: str | None = Field(default=None, max_length=1000)
    target_aweme_id: str | None = Field(default=None, max_length=180)
    source_video_external_id: str | None = Field(default=None, max_length=180)
    started_at: datetime
    page: DouyinExtensionPageSnapshot
    capture_context: DouyinExtensionCaptureContextPayload
    items: list[DouyinExtensionFullModalHarvestItemPayload] = Field(default_factory=list, max_length=500)
    progress: DouyinExtensionFullModalHarvestProgress
    diagnostics: dict[str, Any] = Field(default_factory=dict)
    commit_policy: Literal["legacy_update_existing", "finalized_only"] = "legacy_update_existing"


class DouyinExtensionFullModalHarvestResponse(BaseModel):
    success: bool = True
    ok: bool = True
    code: str | None = None
    stage: str | None = None
    reason: str | None = None
    capture_session_id: UUID | None = None
    capture_session_resolved_by: str | None = None
    capture_inbox_item_id: UUID | None = None
    source_video_external_id: str | None = None
    aweme_id: str | None = None
    metadata_status: str | None = None
    item_created_or_updated: bool = False
    target_count: int = 0
    harvested_count: int = 0
    matched_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    failed_count: int = 0
    duration_updated_count: int = 0
    like_updated_count: int = 0
    comment_updated_count: int = 0
    favorite_updated_count: int = 0
    share_updated_count: int = 0
    unmatched_count: int = 0
    flushed_aweme_ids: list[str] = Field(default_factory=list)
    failure_summaries: list[dict[str, str]] = Field(default_factory=list)
    stopped_reason: str | None = None
    accepted_count: int = 0
    rejected_count: int = 0
    created_count: int = 0
    idempotent_unchanged_count: int = 0
    beta_write_effective_status: str | None = None
    accepted_unchanged_reason: str | None = None
    estimated_views_received_count: int = 0
    estimated_views_persisted_count: int = 0
    accepted_not_persisted_count: int = 0
    view_count_null_received_count: int = 0
    real_view_count_data_quality_received_count: int = 0
    estimated_views_accepted_but_not_persisted: str = "no"
    finalized_metadata_received_count: int = 0
    finalized_metadata_accepted_count: int = 0
    accepted_not_persisted_fields: list[str] = Field(default_factory=list)


class DouyinExtensionShadowEstimatedViewsItem(BaseModel):
    aweme_id: str = Field(min_length=1, max_length=180)
    source_video_external_id: str | None = Field(default=None, min_length=1, max_length=180)
    duration_seconds: float | None = Field(default=None, ge=0)
    like_count: int | None = Field(default=None, ge=0)
    comment_count: int | None = Field(default=None, ge=0)
    favorite_count: int | None = Field(default=None, ge=0)
    share_count: int | None = Field(default=None, ge=0)
    posted: str | int | None = None
    posted_at: datetime | str | None = None
    thumbnail_url_present: Literal["yes", "no"] | None = None
    thumbnail_url_host: str | None = None
    view_count: int | None = Field(default=None, ge=0)
    real_view_count_available: bool = False
    real_view_count_value: int | None = Field(default=None, ge=0)
    real_view_count_data_quality: Literal["trusted_real_view_count", "trusted_zero_only_low_confidence", "real_view_count_null_low_confidence_or_missing"]
    low_confidence_zero_real_view_count_suppressed: bool = False
    estimated_views: int | None = Field(default=None, ge=0)
    estimated_views_formula: Literal["tiered_like_multiplier_v1"] = "tiered_like_multiplier_v1"
    estimated_views_used: bool = True
    real_view_count_overwritten: bool = False
    view_count_data_quality: str | None = None


class DouyinExtensionShadowEstimatedViewsRequest(BaseModel):
    schema_version: Literal["douyin_extension_shadow_estimated_views.v1"] = "douyin_extension_shadow_estimated_views.v1"
    write_mode: Literal["backend_shadow_test"] = "backend_shadow_test"
    production_mutation_allowed: Literal[False] = False
    source: Literal["hybrid_only_dry_run"] = "hybrid_only_dry_run"
    source_run_id: str | None = Field(default=None, max_length=180)
    estimated_views_formula: Literal["tiered_like_multiplier_v1"] = "tiered_like_multiplier_v1"
    items: list[DouyinExtensionShadowEstimatedViewsItem] = Field(default_factory=list, min_length=1, max_length=5)


class DouyinExtensionShadowEstimatedViewsItemResult(BaseModel):
    index: int
    aweme_id: str
    status: Literal["accepted", "rejected"]
    reasons: list[str] = Field(default_factory=list)
    view_count_received: int | None = None
    estimated_views_received: int | None = None
    real_view_count_data_quality: str | None = None


class DouyinExtensionShadowEstimatedViewsResponse(BaseModel):
    ok: bool
    safe_shadow_endpoint_available: Literal["yes"] = "yes"
    backend_call_attempted: Literal["yes"] = "yes"
    write_mode: Literal["backend_shadow_test"] = "backend_shadow_test"
    production_mutation_allowed: Literal[False] = False
    accepted_count: int = 0
    rejected_count: int = 0
    item_count: int = 0
    items: list[DouyinExtensionShadowEstimatedViewsItemResult] = Field(default_factory=list)
    production_mutation_detected: Literal["no"] = "no"
    production_collect_state_mutated: Literal["no"] = "no"
    production_counters_mutated: Literal["no"] = "no"
    collect_job_mutated: Literal["no"] = "no"
    queue_items_marked_complete: Literal["no"] = "no"


class DouyinExtensionHandshakeRequest(BaseModel):
    install_id: str = Field(min_length=8, max_length=160)
    extension_id: str | None = Field(default=None, max_length=160)
    extension_version: str = Field(min_length=1, max_length=40)
    browser_family: DouyinExtensionBrowserFamily = "unknown"
    api_base_url: str | None = Field(default=None, max_length=300)
    client_time: datetime | None = None


class DouyinExtensionStatusResponse(BaseModel):
    status: DouyinExtensionSetupStatus
    connected: bool = False
    install_id: str | None = None
    extension_id: str | None = None
    extension_version: str | None = None
    browser_family: DouyinExtensionBrowserFamily | None = None
    api_base_url: str | None = None
    last_seen_at: datetime | None = None
    stale_after_seconds: int
    backend_checked_at: datetime
    backend_expected_extension_version: str
    backend_supported_extension_versions: list[str]
    version_status: DouyinExtensionVersionStatus
    compatible: bool = False
    recommended_next_action: DouyinExtensionRecommendedAction
    recommended_next_action_label: str
    operator_message: str
    download_available: bool
    download_url: str = "/douyin-extension/download"
    manual_install_required: bool = True
    chrome_extensions_url: str = "chrome://extensions"
    edge_extensions_url: str = "edge://extensions"


class DouyinExtensionManagerHistoryItem(BaseModel):
    event_id: str
    event_type: DouyinExtensionManagerEventType
    status: DouyinExtensionManagerEventStatus
    created_at: datetime
    page_type: DouyinExtensionPageType | None = None
    page_url: str | None = None
    page_title: str | None = None
    supported_capture: bool | None = None
    imported_profile_count: int = 0
    videos_discovered_count: int = 0
    videos_created_count: int = 0
    videos_updated_count: int = 0
    candidates_matched_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    warning: str | None = None
    recommended_next_action: str | None = None
    recommended_next_action_label: str | None = None
    diagnostics_id: str | None = None


class DouyinExtensionManagerHistoryResponse(BaseModel):
    items: list[DouyinExtensionManagerHistoryItem]
    total_count: int


class DouyinExtensionManagerSummaryResponse(BaseModel):
    status: DouyinExtensionStatusResponse
    history: DouyinExtensionManagerHistoryResponse
