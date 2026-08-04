from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.schemas.pipeline_dashboard import PipelineDashboardSeverity, PipelineDashboardStatus


OperatorHomeTone = Literal["good", "warning", "critical", "neutral"]
OperatorHomeStageKey = Literal[
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


class OperatorHomeOverall(BaseModel):
    status: PipelineDashboardStatus
    headline: str
    critical_count: int = 0
    running_count: int = 0
    generated_at: datetime


class OperatorHomeMetric(BaseModel):
    key: str
    label: str
    value: int
    detail: str
    tone: OperatorHomeTone
    href: str | None = None


class OperatorHomePriorityItem(BaseModel):
    id: str
    severity: PipelineDashboardSeverity
    stage_key: OperatorHomeStageKey
    title: str
    detail: str
    count: int
    href: str
    recommended_action: str
    oldest_at: datetime | None = None


class OperatorHomeStage(BaseModel):
    key: OperatorHomeStageKey
    label: str
    status: PipelineDashboardStatus
    waiting_count: int = 0
    running_count: int = 0
    failed_count: int = 0
    review_count: int = 0
    ready_count: int = 0
    href: str


class OperatorHomeActiveWork(BaseModel):
    job_id: UUID
    source_video_id: UUID | None = None
    title: str
    stage_key: OperatorHomeStageKey
    status: str
    progress_percent: int
    current_step: str | None = None
    started_at: datetime | None = None
    updated_at: datetime
    next_action: str
    href: str


class OperatorHomeCheckpoint(BaseModel):
    key: str
    label: str
    count: int
    detail: str
    tone: OperatorHomeTone
    href: str
    oldest_at: datetime | None = None


class OperatorHomeOutputQaSummary(BaseModel):
    passed: int = 0
    warned: int = 0
    failed: int = 0
    ungraded: int = 0
    total: int = 0


class OperatorHomeAttentionBreakdown(BaseModel):
    critical: int = 0
    warning: int = 0
    manual_review: int = 0
    total: int = 0


class OperatorHomeRecentOutput(BaseModel):
    render_output_id: UUID
    source_video_id: UUID
    title: str
    render_status: str
    qa_status: Literal["pass", "warn", "fail", "ungraded"]
    duration_seconds: float | None = None
    finished_at: datetime | None = None
    href: str


class OperatorHomeReadinessItem(BaseModel):
    key: str
    label: str
    status: Literal["ready", "warning", "blocked", "unknown"]
    detail: str
    href: str | None = None


class OperatorHomeSummaryResponse(BaseModel):
    overall: OperatorHomeOverall
    decision_metrics: list[OperatorHomeMetric] = Field(default_factory=list)
    priority_items: list[OperatorHomePriorityItem] = Field(default_factory=list)
    stages: list[OperatorHomeStage] = Field(default_factory=list)
    active_work: OperatorHomeActiveWork | None = None
    manual_checkpoints: list[OperatorHomeCheckpoint] = Field(default_factory=list)
    output_qa_summary: OperatorHomeOutputQaSummary
    attention_breakdown: OperatorHomeAttentionBreakdown
    recent_outputs: list[OperatorHomeRecentOutput] = Field(default_factory=list)
    system_readiness: list[OperatorHomeReadinessItem] = Field(default_factory=list)
    partial_errors: list[str] = Field(default_factory=list)
