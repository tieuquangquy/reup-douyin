from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


OpsHomeStatus = Literal["healthy", "needs_attention", "blocked", "quiet"]
OpsHomeSeverity = Literal["critical", "warning", "info"]
OpsHomeTone = Literal["good", "warn", "danger", "muted", "active"]
OpsHomeDependencyState = Literal["ready", "warning", "critical", "not_observed"]
OpsHomeHiddenRiskState = Literal["clear", "watch", "critical", "not_observed"]
OpsHomeAdmissionStatus = Literal["safe", "caution", "pause"]


class OpsHomeOverall(BaseModel):
    status: OpsHomeStatus
    headline: str
    detail: str
    critical_count: int = 0
    warning_count: int = 0


class OpsHomeFreshness(BaseModel):
    generated_at: datetime
    metrics_generated_at: datetime
    publish_health_generated_at: datetime
    control_queue_generated_at: datetime


class OpsHomeKpi(BaseModel):
    key: str
    label: str
    value: float | int | None = None
    display_value: str
    detail: str
    tone: OpsHomeTone = "muted"
    href: str


class OpsHomeActionItem(BaseModel):
    id: str
    severity: OpsHomeSeverity
    area: str
    title: str
    detail: str
    count: int
    href: str
    recommended_action: str
    oldest_at: datetime | None = None


class OpsHomeJobHealthRow(BaseModel):
    job_type: str
    queued: int = 0
    running: int = 0
    retryable: int = 0
    failed: int = 0
    waiting_review: int = 0
    completed: int = 0
    total: int = 0
    failure_rate_percent: float = 0.0
    average_step_seconds: float = 0.0
    max_step_seconds: float = 0.0
    tone: OpsHomeTone = "muted"
    href: str = "/ops/jobs"


class OpsHomeAccountHealthRow(BaseModel):
    platform_account_id: str
    display_name: str
    platform: str
    account_status: str
    health_status: str
    priority: int = 0
    is_on_hold: bool = False
    cooldown_until: datetime | None = None
    attempts_7d: int = 0
    succeeded_7d: int = 0
    failed_7d: int = 0
    success_rate_percent: float = 0.0
    needs_reconciliation_count: int = 0
    assigned_draft_count: int = 0
    scheduled_draft_count: int = 0
    recent_error_code: str | None = None
    reasons: list[str] = Field(default_factory=list)


class OpsHomeTrendDay(BaseModel):
    day: str
    attempts: int = 0
    succeeded: int = 0
    failed: int = 0
    needs_reconciliation: int = 0


class OpsHomeFailureSignature(BaseModel):
    source: str
    error_code: str
    label: str
    count: int
    href: str


class OpsHomeFetchReason(BaseModel):
    reason: str
    count: int


class OpsHomeFetchAccountRow(BaseModel):
    account_id: str | None = None
    runs_total: int = 0
    blocked_runs: int = 0
    parse_warning_runs: int = 0
    failed_runs: int = 0
    blocked_rate_percent: float = 0.0


class OpsHomeFetchHealth(BaseModel):
    window_runs: int = 0
    blocked_runs: int = 0
    parse_warning_runs: int = 0
    failed_runs: int = 0
    blocked_ratio_percent: float = 0.0
    top_blocked_reasons: list[OpsHomeFetchReason] = Field(default_factory=list)
    by_account: list[OpsHomeFetchAccountRow] = Field(default_factory=list)


class OpsHomeOperationalStatus(BaseModel):
    key: str
    label: str
    status: Literal["ready", "active", "warning", "critical", "quiet"]
    detail: str
    href: str


class OpsHomeQueueHealth(BaseModel):
    queued: int = 0
    running: int = 0
    retryable: int = 0
    waiting_review: int = 0
    failed: int = 0
    oldest_queued_at: datetime | None = None
    running_with_lock: int = 0
    running_without_lock: int = 0
    busy_worker_count: int = 0
    total_retry_attempts: int = 0


class OpsHomeDependencySignal(BaseModel):
    key: str
    label: str
    state: OpsHomeDependencyState
    signal: str
    impact: str
    observed_at: datetime | None = None
    href: str | None = None


class OpsHomeStorageCapacity(BaseModel):
    state: OpsHomeDependencyState = "not_observed"
    total_gb: float | None = None
    free_gb: float | None = None
    used_percent: float | None = None
    minimum_free_gb: float | None = None
    detail: str = "Storage capacity is not observed."


class OpsHomeHiddenRiskSegment(BaseModel):
    key: str
    label: str
    value: int = 0


class OpsHomeHiddenRisk(BaseModel):
    key: str
    label: str
    state: OpsHomeHiddenRiskState = "not_observed"
    value: float | int | None = None
    display_value: str
    detail: str
    href: str
    segments: list[OpsHomeHiddenRiskSegment] = Field(default_factory=list)


class OpsHomeAdmissionVerdict(BaseModel):
    status: OpsHomeAdmissionStatus = "safe"
    label: str = "Safe to accept new work"
    detail: str = "No observed admission-control condition requires throttling."
    reasons: list[str] = Field(default_factory=list)


class OpsHomeSummaryResponse(BaseModel):
    overall: OpsHomeOverall
    freshness: OpsHomeFreshness
    kpis: list[OpsHomeKpi] = Field(default_factory=list)
    action_items: list[OpsHomeActionItem] = Field(default_factory=list)
    job_health: list[OpsHomeJobHealthRow] = Field(default_factory=list)
    account_health: list[OpsHomeAccountHealthRow] = Field(default_factory=list)
    publish_trend: list[OpsHomeTrendDay] = Field(default_factory=list)
    failure_signatures: list[OpsHomeFailureSignature] = Field(default_factory=list)
    fetch_health: OpsHomeFetchHealth = Field(default_factory=OpsHomeFetchHealth)
    operational_status: list[OpsHomeOperationalStatus] = Field(default_factory=list)
    queue_health: OpsHomeQueueHealth = Field(default_factory=OpsHomeQueueHealth)
    dependencies: list[OpsHomeDependencySignal] = Field(default_factory=list)
    storage_capacity: OpsHomeStorageCapacity = Field(default_factory=OpsHomeStorageCapacity)
    hidden_risks: list[OpsHomeHiddenRisk] = Field(default_factory=list)
    admission_verdict: OpsHomeAdmissionVerdict = Field(default_factory=OpsHomeAdmissionVerdict)
