from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from src.enums import RiskFlagType, RiskSeverity


class FilterDateMode(StrEnum):
    ABSOLUTE_RANGE = "absolute_range"
    LAST_N_DAYS = "last_n_days"
    LATEST_N_VIDEOS = "latest_n_videos"


class FilterSortOption(StrEnum):
    SCORE_DESC = "score_desc"
    NEWEST_FIRST = "newest_first"
    VIEWS_DESC = "views_desc"
    ENGAGEMENT_DESC = "engagement_desc"


class TextDensity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class MetricSnapshotInput:
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    favorite_count: int | None = None


@dataclass(frozen=True)
class RiskFlagInput:
    flag_type: RiskFlagType
    severity: RiskSeverity
    status: str = "OPEN"


@dataclass(frozen=True)
class ContentSignals:
    has_speech: bool | None = None
    text_density: TextDensity | None = None
    is_live_replay: bool | None = None
    is_slideshow: bool | None = None
    has_heavy_watermark: bool | None = None
    processing_complexity: str | None = None


@dataclass(frozen=True)
class CandidateSourceRecord:
    source_video_id: UUID | str
    source_profile_id: UUID | str | None
    source_video_external_id: str
    source_url: str
    caption: str | None
    posted_at: datetime | None
    duration_seconds: float | None
    metrics: MetricSnapshotInput
    content_signals: ContentSignals = field(default_factory=ContentSignals)
    risk_flags: list[RiskFlagInput] = field(default_factory=list)
    metadata_json: dict | None = None


@dataclass(frozen=True)
class FilterConfig:
    date_mode: FilterDateMode | None = None
    start_date: datetime | None = None
    end_date: datetime | None = None
    n_days: int | None = None
    n_videos: int | None = None
    min_views: int | None = None
    max_views: int | None = None
    min_likes: int | None = None
    max_likes: int | None = None
    min_comments: int | None = None
    max_comments: int | None = None
    min_shares: int | None = None
    max_shares: int | None = None
    min_duration_seconds: float | None = None
    max_duration_seconds: float | None = None
    min_engagement_rate: float | None = None
    max_engagement_rate: float | None = None
    min_like_rate: float | None = None
    min_comment_rate: float | None = None
    min_share_rate: float | None = None
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
    limit: int = 50
    offset: int = 0

    def __post_init__(self) -> None:
        if self.date_mode == FilterDateMode.ABSOLUTE_RANGE and not (self.start_date or self.end_date):
            raise ValueError("absolute_range requires start_date or end_date")
        if self.date_mode == FilterDateMode.LAST_N_DAYS and (self.n_days is None or self.n_days <= 0):
            raise ValueError("last_n_days requires positive n_days")
        if self.date_mode == FilterDateMode.LATEST_N_VIDEOS and (self.n_videos is None or self.n_videos <= 0):
            raise ValueError("latest_n_videos requires positive n_videos")
        if self.limit <= 0 or self.limit > 500:
            raise ValueError("limit must be between 1 and 500")
        if self.offset < 0:
            raise ValueError("offset must be non-negative")

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("date_mode", "max_text_density", "sort"):
            if data[key] is not None:
                data[key] = str(data[key])
        for key in ("start_date", "end_date"):
            if data[key] is not None:
                data[key] = data[key].isoformat()
        return data


@dataclass(frozen=True)
class ScoreWeights:
    engagement_quality: float = 0.22
    freshness: float = 0.14
    views_normalized: float = 0.14
    like_rate: float = 0.12
    comment_share_quality: float = 0.12
    duration_fit: float = 0.10
    speech_bonus: float = 0.06
    text_complexity_penalty: float = 0.04
    watermark_penalty: float = 0.03
    copyright_risk_penalty: float = 0.03

    def to_dict(self) -> dict[str, float]:
        return asdict(self)


@dataclass(frozen=True)
class ScoreComponent:
    raw_input: dict
    normalized_subscore: float
    weight: float
    weighted_contribution: float


@dataclass(frozen=True)
class ScoreResult:
    score_version: str
    total_score: float
    score_label: str
    breakdown: dict[str, ScoreComponent]
    reasons: list[str]
    warnings: list[str]

    def breakdown_json(self) -> dict:
        return {
            name: {
                "raw_input": component.raw_input,
                "normalized_subscore": component.normalized_subscore,
                "weight": component.weight,
                "weighted_contribution": component.weighted_contribution,
            }
            for name, component in self.breakdown.items()
        }


@dataclass(frozen=True)
class CandidateEvaluation:
    record: CandidateSourceRecord
    matched: bool
    score: ScoreResult
    inclusion_reasons: list[str]
    exclusion_reasons: list[str]
    warnings: list[str]
