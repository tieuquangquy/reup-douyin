from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from src.enums import RiskFlagStatus, RiskFlagType, RiskSeverity, RiskTargetType


@dataclass(frozen=True)
class RiskFinding:
    risk_type: RiskFlagType
    severity: RiskSeverity
    title: str
    description: str
    evidence_summary: str
    scan_source: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RiskTarget:
    target_type: RiskTargetType
    target_id: UUID
    source_video_id: UUID
    workspace_id: UUID


@dataclass(frozen=True)
class RiskGateSummary:
    can_continue: bool
    requires_operator_decision: bool
    blocking_reasons: list[str]
    highest_severity: RiskSeverity | None
    open_counts_by_severity: dict[str, int]
    accepted_with_warning: bool = False


ACTIVE_RISK_STATUSES = {RiskFlagStatus.OPEN, RiskFlagStatus.ACKNOWLEDGED}
BLOCKING_SEVERITIES = {RiskSeverity.CRITICAL, RiskSeverity.BLOCKING}
STRONG_WARNING_SEVERITIES = {RiskSeverity.HIGH}
