from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.enums import OperatorRiskDecisionType, RiskFlagStatus, RiskFlagType, RiskSeverity, RiskTargetType


class RiskScanRequest(BaseModel):
    target_type: RiskTargetType
    target_id: UUID
    scope: str | None = None


class RiskFlagActionRequest(BaseModel):
    note: str | None = None


class RiskDecisionRequest(BaseModel):
    target_type: RiskTargetType
    target_id: UUID
    decision_type: OperatorRiskDecisionType
    note: str | None = None
    decided_by: str | None = "local_operator"


class RiskGateSummaryResponse(BaseModel):
    can_continue: bool
    requires_operator_decision: bool
    blocking_reasons: list[str]
    highest_severity: RiskSeverity | None
    open_counts_by_severity: dict[str, int]
    accepted_with_warning: bool = False


class RiskFlagResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_video_id: UUID
    target_type: RiskTargetType
    target_id: UUID | None
    scan_run_id: UUID | None
    flag_type: RiskFlagType
    severity: RiskSeverity
    status: RiskFlagStatus
    title: str | None
    description: str | None
    reason: str | None
    evidence_summary: str | None
    scan_source: str | None
    detected_at: datetime | None
    resolved_at: datetime | None
    resolution_note: str | None
    evidence_json: dict | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class RiskFlagListResponse(BaseModel):
    flags: list[RiskFlagResponse]


class OperatorRiskDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_video_id: UUID
    target_type: RiskTargetType
    target_id: UUID
    decision_type: OperatorRiskDecisionType
    note: str | None
    decided_by: str | None
    decided_at: datetime
    gate_summary_json: dict | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class RiskSummaryResponse(BaseModel):
    target_type: RiskTargetType
    target_id: UUID
    flags: list[RiskFlagResponse]
    gate: RiskGateSummaryResponse
    latest_decision: OperatorRiskDecisionResponse | None = None


class RiskScanResponse(RiskSummaryResponse):
    scan_run_id: UUID
