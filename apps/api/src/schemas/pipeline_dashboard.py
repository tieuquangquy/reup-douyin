from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

PipelineDashboardStatus = Literal["healthy", "needs_attention", "blocked", "quiet", "in_progress"]
PipelineDashboardSeverity = Literal["info", "warning", "critical"]
PipelineStageKey = Literal[
    "capture",
    "review",
    "reup_queue",
    "download",
    "audio_analysis",
    "translate",
    "tts",
    "ocr",
    "render",
    "output_review",
    "draft",
    "export_package",
    "publish_handoff",
]


class PipelineDashboardMetric(BaseModel):
    key: str
    label: str
    value: int
    detail: str | None = None


class PipelineDashboardStage(BaseModel):
    key: PipelineStageKey
    label: str
    description: str
    status: PipelineDashboardStatus
    primary_count: int
    primary_label: str
    secondary_count: int
    secondary_label: str
    metrics: list[PipelineDashboardMetric] = Field(default_factory=list)
    attention_count: int = 0
    waiting_count: int = 0
    running_count: int = 0
    review_count: int = 0
    failed_count: int = 0
    ready_count: int = 0
    total_count: int = 0
    href: str
    next_action: str


class PipelineDashboardOutputQaSummary(BaseModel):
    passed: int = 0
    warned: int = 0
    failed: int = 0
    ungraded: int = 0
    total: int = 0


class PipelineDashboardAttentionItem(BaseModel):
    id: str
    severity: PipelineDashboardSeverity
    stage_key: PipelineStageKey
    title: str
    detail: str
    count: int
    href: str
    recommended_action: str


class PipelineDashboardActivityItem(BaseModel):
    id: str
    stage_key: PipelineStageKey
    title: str
    detail: str
    occurred_at: datetime
    href: str


class PipelineDashboardQuickLink(BaseModel):
    label: str
    href: str
    description: str
    stage_key: PipelineStageKey | None = None


class PipelineDashboardResponse(BaseModel):
    generated_at: datetime
    overall_status: PipelineDashboardStatus
    headline: str
    summary_metrics: list[PipelineDashboardMetric] = Field(default_factory=list)
    stages: list[PipelineDashboardStage] = Field(default_factory=list)
    attention_items: list[PipelineDashboardAttentionItem] = Field(default_factory=list)
    output_qa_summary: PipelineDashboardOutputQaSummary = Field(default_factory=PipelineDashboardOutputQaSummary)
    recent_activity: list[PipelineDashboardActivityItem] = Field(default_factory=list)
    quick_links: list[PipelineDashboardQuickLink] = Field(default_factory=list)
