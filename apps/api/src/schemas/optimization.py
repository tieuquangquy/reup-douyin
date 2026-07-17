from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class OutcomeScoreComponentResponse(BaseModel):
    key: str
    label: str
    raw_input: dict
    subscore: float
    weight: float
    weighted_contribution: float


class OutcomeScoreResponse(BaseModel):
    target_id: UUID
    target_type: str
    publish_draft_id: UUID
    source_video_id: UUID
    score_version: str
    total_outcome_score: float
    outcome_label: str
    breakdown: list[OutcomeScoreComponentResponse]
    improvement_hints: list[str]
    warnings: list[str]


class OutcomeGroupSummary(BaseModel):
    group_key: str
    label: str
    item_count: int = 0
    average_outcome_score: float | None = None
    strong_count: int = 0
    weak_count: int = 0
    published_count: int = 0
    needs_attention_count: int = 0
    hints: list[str] = Field(default_factory=list)


class OutcomeSummariesResponse(BaseModel):
    generated_at: datetime
    score_version: str
    by_source_profile: list[OutcomeGroupSummary]
    by_niche: list[OutcomeGroupSummary]
    by_preset: list[OutcomeGroupSummary]
    by_account: list[OutcomeGroupSummary]
    by_score_bucket: list[OutcomeGroupSummary]


class RoutingHintAccount(BaseModel):
    platform_account_id: UUID
    display_name: str
    confidence_score: float
    confidence_label: str
    health_status: str
    reasons: list[str]
    warnings: list[str]


class RoutingHintsResponse(BaseModel):
    publish_draft_id: UUID
    recommended_accounts: list[RoutingHintAccount]
    blocked_accounts: list[RoutingHintAccount]
    automation_policy: dict
    explanation: list[str]


class SchedulingSlotHint(BaseModel):
    platform_account_id: UUID | None = None
    account_name: str | None = None
    suggested_publish_at: datetime
    confidence_label: str
    reasons: list[str]
    warnings: list[str]


class SchedulingHintsResponse(BaseModel):
    publish_draft_id: UUID
    suggested_slots: list[SchedulingSlotHint]
    automation_policy: dict
    explanation: list[str]


class ManualTouchHotspot(BaseModel):
    area: str
    count: int
    severity: str
    hint: str


class ManualTouchSummaryResponse(BaseModel):
    generated_at: datetime
    hotspots: list[ManualTouchHotspot]


class PresetFeedbackItem(BaseModel):
    preset_name: str
    item_count: int
    average_outcome_score: float | None
    strong_count: int
    weak_count: int
    tuning_hints: list[str]


class PresetFeedbackResponse(BaseModel):
    generated_at: datetime
    items: list[PresetFeedbackItem]


class OptimizationDashboardResponse(BaseModel):
    generated_at: datetime
    outcome_summaries: OutcomeSummariesResponse
    preset_feedback: PresetFeedbackResponse
    manual_touch_summary: ManualTouchSummaryResponse
    ready_draft_routing_hints: list[RoutingHintsResponse]

