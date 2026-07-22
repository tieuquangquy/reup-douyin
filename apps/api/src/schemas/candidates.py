from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.enums import CandidateStatus
from src.services.candidate_types import FilterDateMode, FilterSortOption, TextDensity


class FilterConfigRequest(BaseModel):
    date_mode: FilterDateMode | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    n_days: int | None = Field(default=None, gt=0)
    n_videos: int | None = Field(default=None, gt=0)
    min_views: int | None = Field(default=None, ge=0)
    max_views: int | None = Field(default=None, ge=0)
    min_likes: int | None = Field(default=None, ge=0)
    max_likes: int | None = Field(default=None, ge=0)
    min_comments: int | None = Field(default=None, ge=0)
    max_comments: int | None = Field(default=None, ge=0)
    min_shares: int | None = Field(default=None, ge=0)
    max_shares: int | None = Field(default=None, ge=0)
    min_duration_seconds: float | None = Field(default=None, ge=0)
    max_duration_seconds: float | None = Field(default=None, ge=0)
    min_engagement_rate: float | None = Field(default=None, ge=0, le=1)
    max_engagement_rate: float | None = Field(default=None, ge=0, le=1)
    min_like_rate: float | None = Field(default=None, ge=0)
    min_comment_rate: float | None = Field(default=None, ge=0)
    min_share_rate: float | None = Field(default=None, ge=0)
    has_speech: bool | None = None
    require_speech: bool = False
    allow_no_speech: bool = True
    max_text_density: TextDensity | None = None
    exclude_live_replay: bool = True
    exclude_slideshow: bool = True
    exclude_heavy_watermark: bool = True
    exclude_high_copyright_risk: bool = True
    exclude_high_processing_complexity: bool = True
    sort: FilterSortOption = FilterSortOption.SCORE_DESC
    limit: int = Field(default=50, ge=1, le=500)
    offset: int = Field(default=0, ge=0)


class CandidateFilterRequest(BaseModel):
    preset_name: str | None = None
    filter_config: FilterConfigRequest | None = None
    source_profile_id: UUID | None = None
    persist: bool = True


class CandidateScoreResponse(BaseModel):
    source_video_id: UUID | str
    source_video_external_id: str
    source_url: str
    caption: str | None
    posted_at: datetime | None
    duration_seconds: float | None
    total_score: float
    score_label: str
    score_version: str
    score_breakdown: dict
    inclusion_reasons: list[str]
    exclusion_reasons: list[str]
    warnings: list[str]
    metrics: dict


class CandidateFilterResponse(BaseModel):
    total_count: int
    matched_count: int
    rejected_count: int
    rejection_summary: dict[str, int]
    results: list[CandidateScoreResponse]


class PersistedCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_video_id: UUID
    status: CandidateStatus
    score: float | None
    score_version: str | None
    score_label: str | None
    score_breakdown_json: dict | None
    score_reason: str | None
    preset_name: str | None
    filter_config_json: dict | None
    inclusion_reasons_json: list | None
    exclusion_reasons_json: list | None
    warnings_json: list | None
    evaluated_at: datetime | None
    priority: int
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class CandidateSourceVideoSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_profile_id: UUID
    source_video_external_id: str
    source_url: str
    caption: str | None
    posted_at: datetime | None
    duration_seconds: float | None
    metadata_json: dict | None


class CandidateSummaryResponse(BaseModel):
    id: UUID
    source_video_id: UUID
    status: CandidateStatus
    score: float | None
    score_label: str | None
    priority: int
    preset_name: str | None
    reup_score: float | None = None
    caption: str | None = None
    thumbnail_url: str | None = None
    posted_display: str | None = None
    duration_text: str | None = None
    estimated_views_display: str | None = None
    estimated_views_min: int | None = None
    estimated_views_max: int | None = None
    estimated_views_mid: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    engagement_rate: float | None = None
    duration_seconds: float | None = None
    aweme_id: str | None = None
    source_video_external_id: str | None = None
    source_url: str | None = None
    review_status: str | None = None
    decision_status: str | None = None
    in_reup_queue: bool = False
    reup_queue_item_id: UUID | None = None
    reup_queue_status: str | None = None
    updated_at: datetime
    evaluated_at: datetime | None = None
    source_video: CandidateSourceVideoSummary | None = None

    @classmethod
    def from_candidate(cls, candidate, *, reup_queue_membership=None) -> "CandidateSummaryResponse":
        metadata = candidate.metadata_json or {}
        source = candidate.source_video
        source_metadata = (source.metadata_json or {}) if source else {}
        nested_source_metadata = source_metadata.get("source_metadata") if isinstance(source_metadata.get("source_metadata"), dict) else {}
        caption = _first_present(
            metadata.get("caption"),
            nested_source_metadata.get("caption"),
            source.caption if source else None,
        )
        reup_score = _first_present(
            metadata.get("reup_score"),
            nested_source_metadata.get("reup_score"),
            source_metadata.get("reup_score"),
        )
        thumbnail_url = _string_metadata(metadata, nested_source_metadata, source_metadata, key="thumbnail_url")
        posted_display = _string_metadata(metadata, nested_source_metadata, source_metadata, key="posted_display")
        if posted_display is None and source and source.posted_at:
            posted_display = source.posted_at.isoformat()
        duration_text = _string_metadata(metadata, nested_source_metadata, source_metadata, key="duration_text")
        estimated_views_display = _string_metadata(
            metadata,
            nested_source_metadata,
            source_metadata,
            key="estimated_views_display",
        )
        estimated_views_min = _first_present(
            metadata.get("estimated_views_min"),
            nested_source_metadata.get("estimated_views_min"),
            source_metadata.get("estimated_views_min"),
        )
        estimated_views_max = _first_present(
            metadata.get("estimated_views_max"),
            nested_source_metadata.get("estimated_views_max"),
            source_metadata.get("estimated_views_max"),
        )
        estimated_views_mid = _first_present(
            metadata.get("estimated_views_mid"),
            nested_source_metadata.get("estimated_views_mid"),
            source_metadata.get("estimated_views_mid"),
        )
        if estimated_views_mid is None and estimated_views_min is not None and estimated_views_max is not None:
            estimated_views_mid = int(round((int(estimated_views_min) + int(estimated_views_max)) / 2))
        like_count = _first_present(
            metadata.get("like_count"),
            nested_source_metadata.get("like_count"),
            source_metadata.get("like_count"),
        )
        comment_count = _first_present(
            metadata.get("comment_count"),
            nested_source_metadata.get("comment_count"),
            source_metadata.get("comment_count"),
        )
        share_count = _first_present(
            metadata.get("share_count"),
            nested_source_metadata.get("share_count"),
            source_metadata.get("share_count"),
        )
        engagement_rate = _first_present(
            metadata.get("engagement_rate"),
            nested_source_metadata.get("engagement_rate"),
            source_metadata.get("engagement_rate"),
        )
        duration_seconds = _first_present(
            metadata.get("duration_seconds"),
            nested_source_metadata.get("duration_seconds"),
            source_metadata.get("duration_seconds"),
            source.duration_seconds if source else None,
        )
        if engagement_rate is None and estimated_views_mid and int(estimated_views_mid) > 0:
            metric_total = sum(
                int(value)
                for value in (like_count, comment_count, share_count)
                if value is not None
            )
            if metric_total > 0:
                engagement_rate = metric_total / float(estimated_views_mid)
        aweme_id = _first_present(
            metadata.get("aweme_id"),
            nested_source_metadata.get("aweme_id"),
            source.source_video_external_id if source else None,
        )
        source_url = _first_present(
            metadata.get("source_url"),
            nested_source_metadata.get("source_url"),
            source.source_url if source else None,
        )
        source_video_summary = CandidateSourceVideoSummary.model_validate(source) if source is not None else None
        membership = reup_queue_membership
        return cls(
            id=candidate.id,
            source_video_id=candidate.source_video_id,
            status=candidate.status,
            score=candidate.score,
            score_label=candidate.score_label,
            priority=candidate.priority,
            preset_name=candidate.preset_name,
            reup_score=reup_score,
            caption=caption,
            thumbnail_url=thumbnail_url,
            posted_display=posted_display,
            duration_text=duration_text,
            estimated_views_display=estimated_views_display,
            estimated_views_min=estimated_views_min,
            estimated_views_max=estimated_views_max,
            estimated_views_mid=estimated_views_mid,
            like_count=like_count,
            comment_count=comment_count,
            share_count=share_count,
            engagement_rate=engagement_rate,
            duration_seconds=duration_seconds,
            aweme_id=aweme_id,
            source_video_external_id=source.source_video_external_id if source else None,
            source_url=source_url,
            review_status=metadata.get("review_status"),
            decision_status=metadata.get("decision_status"),
            in_reup_queue=bool(getattr(membership, "in_reup_queue", False)),
            reup_queue_item_id=getattr(membership, "reup_queue_item_id", None),
            reup_queue_status=(
                membership.reup_queue_status.value
                if getattr(membership, "reup_queue_status", None) is not None
                else None
            ),
            updated_at=candidate.updated_at,
            evaluated_at=candidate.evaluated_at,
            source_video=source_video_summary,
        )


class CandidateDetailResponse(PersistedCandidateResponse):
    source_video: CandidateSourceVideoSummary | None = None
    in_reup_queue: bool = False
    reup_queue_item_id: UUID | None = None
    reup_queue_status: str | None = None
    capture_item_id: str | None = None
    capture_session_id: str | None = None
    source: str | None = None
    source_module: str | None = None
    aweme_id: str | None = None
    source_video_external_id: str | None = None
    source_url: str | None = None
    video_url: str | None = None
    profile_url: str | None = None
    profile_name: str | None = None
    caption: str | None = None
    title: str | None = None
    description: str | None = None
    thumbnail_url: str | None = None
    thumbnail: str | None = None
    posted_at: str | None = None
    posted_display_exact: str | None = None
    posted_display: str | None = None
    postedDisplay: str | None = None
    posted: str | None = None
    posted_text: str | None = None
    posted_text_raw: str | None = None
    duration_seconds: float | None = None
    durationSeconds: float | None = None
    duration_text: str | None = None
    durationText: str | None = None
    duration: str | None = None
    view_count: int | None = None
    view_count_text: str | None = None
    estimated_views_text_raw: str | None = None
    estimated_views_display: str | None = None
    views_display: str | None = None
    estimated_views_min: int | None = None
    estimated_views_max: int | None = None
    estimated_views_mid: int | None = None
    views_mid: int | None = None
    estimated_views_parse_confidence: str | None = None
    like_count: int | None = None
    likes: int | None = None
    like_count_text: str | None = None
    comment_count: int | None = None
    comments: int | None = None
    comment_count_text: str | None = None
    share_count: int | None = None
    shares: int | None = None
    share_count_text: str | None = None
    favorite_count: int | None = None
    favorite_count_text: str | None = None
    engagement_score: float | int | None = None
    engagement_rate: float | None = None
    reup_score: float | int | None = None
    reup_score_label: str | None = None
    reup_score_level: str | None = None
    reup_score_components: dict | None = None
    reup_score_reasons: list | None = None
    review_status: str | None = None
    decision_status: str | None = None
    preset: str | None = None
    matched_presets: list | None = None
    has_thumbnail: bool | None = None
    has_posted: bool | None = None
    has_duration: bool | None = None
    has_estimated_views: bool | None = None
    has_likes: bool | None = None
    has_comments: bool | None = None
    has_shares: bool | None = None
    has_all_core_metadata: bool | None = None
    missing_metadata_fields: list | None = None
    source_metadata: dict[str, Any] | None = None
    capture_to_review_comparison: dict[str, Any] | None = None
    review_board_trace_version: str | None = None
    review_candidate_debug: dict[str, Any] | None = None
    review_board_api_debug: dict[str, Any] | None = None

    @model_validator(mode="after")
    def hydrate_review_candidate_metadata(self) -> "CandidateDetailResponse":
        candidate_metadata = self.metadata_json or {}
        nested_source_metadata = candidate_metadata.get("source_metadata") if isinstance(candidate_metadata.get("source_metadata"), dict) else {}
        source_video_metadata = self.source_video.metadata_json if self.source_video else None
        source_video_metadata = source_video_metadata or {}
        source_video_snapshot = source_video_metadata.get("source_metadata") if isinstance(source_video_metadata.get("source_metadata"), dict) else {}
        source_metadata = nested_source_metadata or source_video_snapshot or source_video_metadata
        self.source_metadata = source_metadata or None
        self.capture_to_review_comparison = candidate_metadata.get("capture_to_review_comparison") or source_video_metadata.get("capture_to_review_comparison")
        source = self.source_video
        for field in _REVIEW_CANDIDATE_METADATA_FIELDS:
            snapshot_value = source_metadata.get(field)
            if snapshot_value is not None:
                setattr(self, field, snapshot_value)
            elif getattr(self, field) is None:
                setattr(self, field, candidate_metadata.get(field))
        exact_posted_display = _first_present(source_metadata.get("posted_display_exact"), candidate_metadata.get("posted_display_exact"), self.posted_display_exact)
        if exact_posted_display is not None:
            self.posted_display_exact = exact_posted_display
            self.posted_display = exact_posted_display
        if self.source_video_external_id is None and source is not None:
            self.source_video_external_id = source.source_video_external_id
        if self.aweme_id is None:
            self.aweme_id = self.source_video_external_id
        if self.source_url is None and source is not None:
            self.source_url = source.source_url
        if self.video_url is None:
            self.video_url = self.source_url
        if self.caption is None and source is not None:
            self.caption = source.caption
        if self.thumbnail_url is None:
            self.thumbnail_url = _string_metadata(candidate_metadata, source_metadata, key="thumbnail_url")
        if self.posted_display is None and source and source.posted_at:
            self.posted_display = source.posted_at.isoformat()
        if self.duration_seconds is None and source is not None:
            self.duration_seconds = source.duration_seconds
        self.postedDisplay = self.posted_display
        self.durationSeconds = self.duration_seconds
        self.durationText = self.duration_text
        self.thumbnail = self.thumbnail or self.thumbnail_url
        self.posted = self.posted or self.posted_display or self.posted_text
        self.duration = self.duration or self.duration_text
        self.views_display = self.views_display or self.estimated_views_display
        self.views_mid = self.views_mid if self.views_mid is not None else self.estimated_views_mid
        self.likes = self.likes if self.likes is not None else self.like_count
        self.comments = self.comments if self.comments is not None else self.comment_count
        self.shares = self.shares if self.shares is not None else self.share_count
        self.review_board_trace_version = "22F-1H"
        self.review_candidate_debug = _review_candidate_debug(self, candidate_metadata, source_metadata)
        return self


_REVIEW_CANDIDATE_METADATA_FIELDS = (
    "capture_item_id",
    "capture_session_id",
    "source",
    "source_module",
    "aweme_id",
    "source_video_external_id",
    "source_url",
    "video_url",
    "profile_url",
    "profile_name",
    "caption",
    "title",
    "description",
    "thumbnail_url",
    "thumbnail",
    "posted_at",
    "posted_display_exact",
    "posted_display",
    "posted",
    "posted_text",
    "posted_text_raw",
    "duration_seconds",
    "duration_text",
    "duration",
    "view_count",
    "view_count_text",
    "estimated_views_text_raw",
    "estimated_views_display",
    "views_display",
    "estimated_views_min",
    "estimated_views_max",
    "estimated_views_mid",
    "views_mid",
    "estimated_views_parse_confidence",
    "like_count",
    "likes",
    "like_count_text",
    "comment_count",
    "comments",
    "comment_count_text",
    "share_count",
    "shares",
    "share_count_text",
    "favorite_count",
    "favorite_count_text",
    "engagement_score",
    "engagement_rate",
    "reup_score",
    "reup_score_label",
    "reup_score_level",
    "reup_score_components",
    "reup_score_reasons",
    "review_status",
    "decision_status",
    "preset",
    "matched_presets",
    "has_thumbnail",
    "has_posted",
    "has_duration",
    "has_estimated_views",
    "has_likes",
    "has_comments",
    "has_shares",
    "has_all_core_metadata",
    "missing_metadata_fields",
)


def _review_candidate_debug(response: CandidateDetailResponse, candidate_metadata: dict[str, Any], source_metadata: dict[str, Any]) -> dict[str, Any]:
    visible_score_source = _field_source("reup_score", response, candidate_metadata, source_metadata)
    estimated_views_source = _estimated_views_source(response, candidate_metadata, source_metadata)
    posted_source = _posted_display_source(response, candidate_metadata, source_metadata)
    source_posted_display = _string_metadata(source_metadata, key="posted_display")
    source_posted_display_exact = _string_metadata(source_metadata, key="posted_display_exact")
    duration_source = _duration_source(response, candidate_metadata, source_metadata)
    hydration_debug = candidate_metadata.get("review_board_hydration_debug") or {}
    return {
        "traceVersion": "22F-1H",
        "apiEndpoint": "GET /candidates",
        "candidateId": str(response.id),
        "captureItemId": response.capture_item_id,
        "awemeId": response.aweme_id,
        "hydrationAttempted": hydration_debug.get("attempted", False),
        "hydrated": hydration_debug.get("hydrated", False),
        "hydrationMatchKey": hydration_debug.get("match_key"),
        "hydrationCaptureItemId": hydration_debug.get("capture_item_id"),
        "hydrationUpdatedFields": hydration_debug.get("updated_fields", []),
        "hydrationReasonIfSkipped": hydration_debug.get("reason_if_not_matched"),
        "hydration_lookup": hydration_debug,
        "visibleScore": response.reup_score,
        "visibleScoreSource": visible_score_source,
        "scoreSource": visible_score_source,
        "scoreValue": response.reup_score,
        "rawCandidateScore": response.score,
        "rawCandidateReupScore": response.reup_score,
        "rawCandidatePriorityScore": response.priority,
        "estimatedViewsDisplay": response.estimated_views_display,
        "estimatedViewsSource": estimated_views_source,
        "metricsSource": _metrics_source(response, candidate_metadata, source_metadata),
        "likeCount": response.like_count,
        "commentCount": response.comment_count,
        "shareCount": response.share_count,
        "postedDisplay": response.posted_display,
        "postedDisplaySource": posted_source,
        "postedDisplayValue": response.posted_display,
        "postedAtValue": response.posted_at,
        "postedDisplayExactValue": response.posted_display_exact,
        "postedDisplayWasFormatted": bool(response.posted_display and not source_posted_display_exact and not source_posted_display and posted_source in {"source_metadata.posted_at", "candidate.metadata_json.posted_at", "candidate.posted_at"}),
        "durationText": response.duration_text,
        "durationSource": duration_source,
        "durationValue": response.duration_text or response.duration_seconds,
        "sourceMetadataPresent": bool(source_metadata),
        "sourceMetadataVersion": source_metadata.get("source_metadata_version"),
        "capture_to_review_comparison": candidate_metadata.get("capture_to_review_comparison"),
        "candidateMetadataKeys": sorted(candidate_metadata.keys()),
        "sourceMetadataKeys": sorted(source_metadata.keys()),
        "rawCandidateKeys": sorted(set(candidate_metadata.keys()) | {"id", "source_video_id", "status", "score", "priority", "metadata_json"}),
    }


def _field_source(field: str, response: CandidateDetailResponse, candidate_metadata: dict[str, Any], source_metadata: dict[str, Any], *, fallback_field: str | None = None) -> str:
    if source_metadata.get(field) is not None:
        return f"source_metadata.{field}"
    if candidate_metadata.get(field) is not None:
        return f"candidate.metadata_json.{field}"
    if getattr(response, field, None) is not None:
        return f"candidate.{field}"
    if fallback_field and getattr(response, fallback_field, None) is not None:
        return f"candidate.{fallback_field}"
    return "missing"


def _metrics_source(response: CandidateDetailResponse, candidate_metadata: dict[str, Any], source_metadata: dict[str, Any]) -> str:
    for field in ("like_count", "comment_count", "share_count"):
        source = _field_source(field, response, candidate_metadata, source_metadata)
        if source != "missing":
            return source.rsplit(".", 1)[0]
    return "missing"


def _estimated_views_source(response: CandidateDetailResponse, candidate_metadata: dict[str, Any], source_metadata: dict[str, Any]) -> str:
    for field in ("estimated_views_display", "estimated_views_min", "estimated_views_max", "estimated_views_mid"):
        source = _field_source(field, response, candidate_metadata, source_metadata)
        if source != "missing":
            return source
    return "missing"


def _posted_display_source(response: CandidateDetailResponse, candidate_metadata: dict[str, Any], source_metadata: dict[str, Any]) -> str:
    for field in ("posted_display_exact", "posted_display", "posted_text_raw"):
        source = _field_source(field, response, candidate_metadata, source_metadata)
        if source != "missing":
            return source
    return _field_source("posted_at", response, candidate_metadata, source_metadata)


def _duration_source(response: CandidateDetailResponse, candidate_metadata: dict[str, Any], source_metadata: dict[str, Any]) -> str:
    for field in ("duration_text", "duration_seconds"):
        source = _field_source(field, response, candidate_metadata, source_metadata)
        if source != "missing":
            return source
    return "missing"


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _string_metadata(*payloads: dict[str, Any], key: str) -> str | None:
    value = _first_present(*(payload.get(key) for payload in payloads))
    return value if isinstance(value, str) and value.strip() else None


class CandidateBulkStatusRequest(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=500)
    status: CandidateStatus


class CandidateBulkStatusResponse(BaseModel):
    updated_count: int
    candidates: list[CandidateDetailResponse]


class CandidateListResponse(BaseModel):
    view: Literal["summary", "detail"] = "summary"
    total_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    offset: int = 0
    limit: int = 0
    candidates: list[CandidateSummaryResponse] | list[CandidateDetailResponse]
    review_board_trace_version: str = "22F-3A"
    review_board_api_debug: dict[str, Any] | None = None
    review_board_hydration_summary: dict[str, Any] | None = None


class CandidateDeleteResponse(BaseModel):
    candidate: CandidateDetailResponse
    message: str


class FilterPresetResponse(BaseModel):
    name: str
    description: str
    use_when: str
    filter_config: dict
    score_weights: dict[str, float]


class FilterPresetListResponse(BaseModel):
    presets: list[FilterPresetResponse]
