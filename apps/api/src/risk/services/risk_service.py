from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import OperatorRiskDecisionType, RiskFlagStatus, RiskTargetType
from src.models.ingestion import SourceVideo
from src.models.media import RenderOutput
from src.models.publish import PublishDraft
from src.models.review import OperatorRiskDecision, RiskFlag
from src.risk.scanners.rule_based import scan_publish_draft, scan_render_output, scan_source_video
from src.risk.services.policy import evaluate_gate
from src.risk.types import RiskFinding, RiskGateSummary, RiskTarget


class RiskServiceError(ValueError):
    pass


class RiskService:
    def __init__(self, db: Session):
        self.db = db

    def run_scan(self, target_type: RiskTargetType, target_id: UUID) -> tuple[UUID, list[RiskFlag], RiskGateSummary]:
        target = self._resolve_target(target_type, target_id)
        scan_run_id = uuid4()
        findings = self._scan_target(target_type, target_id)
        self._mark_stale_open_flags(target)
        flags = [self._create_flag(target, finding, scan_run_id) for finding in findings]
        self.db.commit()
        current_flags = self.list_flags(target_type=target_type, target_id=target_id)
        return scan_run_id, current_flags, self.gate_summary(target_type, target_id)

    def list_flags(
        self,
        *,
        target_type: RiskTargetType | None = None,
        target_id: UUID | None = None,
        severity: str | None = None,
        status: RiskFlagStatus | None = None,
    ) -> list[RiskFlag]:
        stmt = select(RiskFlag).order_by(RiskFlag.created_at.desc())
        if target_type is not None:
            stmt = stmt.where(RiskFlag.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(RiskFlag.target_id == target_id)
        if severity is not None:
            stmt = stmt.where(RiskFlag.severity == severity)
        if status is not None:
            stmt = stmt.where(RiskFlag.status == status)
        return list(self.db.scalars(stmt))

    def get_flag(self, flag_id: UUID) -> RiskFlag:
        flag = self.db.get(RiskFlag, flag_id)
        if flag is None:
            raise RiskServiceError("Risk flag not found")
        return flag

    def update_flag_status(self, flag_id: UUID, status: RiskFlagStatus, note: str | None = None) -> RiskFlag:
        flag = self.get_flag(flag_id)
        flag.status = status
        if status in {RiskFlagStatus.RESOLVED, RiskFlagStatus.WAIVED, RiskFlagStatus.REJECTED}:
            flag.resolved_at = datetime.now(UTC)
        flag.resolution_note = note
        self.db.commit()
        self.db.refresh(flag)
        return flag

    def create_decision(
        self,
        *,
        target_type: RiskTargetType,
        target_id: UUID,
        decision_type: OperatorRiskDecisionType,
        note: str | None,
        decided_by: str | None = "local_operator",
    ) -> OperatorRiskDecision:
        target = self._resolve_target(target_type, target_id)
        flags = self.list_flags(target_type=target_type, target_id=target_id)
        gate = evaluate_gate(flags)
        decision = OperatorRiskDecision(
            workspace_id=target.workspace_id,
            source_video_id=target.source_video_id,
            target_type=target_type,
            target_id=target_id,
            decision_type=decision_type,
            note=note,
            decided_by=decided_by,
            decided_at=datetime.now(UTC),
            gate_summary_json=gate.__dict__,
        )
        self.db.add(decision)
        self.db.commit()
        self.db.refresh(decision)
        return decision

    def latest_decision(self, target_type: RiskTargetType, target_id: UUID) -> OperatorRiskDecision | None:
        return self.db.scalar(
            select(OperatorRiskDecision)
            .where(OperatorRiskDecision.target_type == target_type, OperatorRiskDecision.target_id == target_id)
            .order_by(OperatorRiskDecision.decided_at.desc())
            .limit(1)
        )

    def gate_summary(self, target_type: RiskTargetType, target_id: UUID) -> RiskGateSummary:
        flags = self.list_flags(target_type=target_type, target_id=target_id)
        return evaluate_gate(flags, self.latest_decision(target_type, target_id))

    def _resolve_target(self, target_type: RiskTargetType, target_id: UUID) -> RiskTarget:
        if target_type == RiskTargetType.SOURCE_VIDEO:
            source_video = self.db.get(SourceVideo, target_id)
            if source_video is None:
                raise RiskServiceError("Source video not found")
            return RiskTarget(target_type=target_type, target_id=source_video.id, source_video_id=source_video.id, workspace_id=source_video.workspace_id)
        if target_type == RiskTargetType.RENDER_OUTPUT:
            render = self.db.get(RenderOutput, target_id)
            if render is None:
                raise RiskServiceError("Render output not found")
            return RiskTarget(target_type=target_type, target_id=render.id, source_video_id=render.source_video_id, workspace_id=render.workspace_id)
        draft = self.db.get(PublishDraft, target_id)
        if draft is None:
            raise RiskServiceError("Publish draft not found")
        return RiskTarget(target_type=target_type, target_id=draft.id, source_video_id=draft.source_video_id, workspace_id=draft.workspace_id)

    def _scan_target(self, target_type: RiskTargetType, target_id: UUID) -> list[RiskFinding]:
        if target_type == RiskTargetType.SOURCE_VIDEO:
            return scan_source_video(self.db.get(SourceVideo, target_id))
        if target_type == RiskTargetType.RENDER_OUTPUT:
            return scan_render_output(self.db.get(RenderOutput, target_id))
        return scan_publish_draft(self.db.get(PublishDraft, target_id))

    def _mark_stale_open_flags(self, target: RiskTarget) -> None:
        for flag in self.list_flags(target_type=target.target_type, target_id=target.target_id, status=RiskFlagStatus.OPEN):
            flag.status = RiskFlagStatus.RESOLVED
            flag.resolved_at = datetime.now(UTC)
            flag.resolution_note = "Superseded by a newer risk scan run."
        self.db.flush()

    def _create_flag(self, target: RiskTarget, finding: RiskFinding, scan_run_id: UUID) -> RiskFlag:
        flag = RiskFlag(
            workspace_id=target.workspace_id,
            source_video_id=target.source_video_id,
            target_type=target.target_type,
            target_id=target.target_id,
            scan_run_id=scan_run_id,
            flag_type=finding.risk_type,
            severity=finding.severity,
            status=RiskFlagStatus.OPEN,
            title=finding.title,
            description=finding.description,
            reason=finding.description,
            evidence_summary=finding.evidence_summary,
            scan_source=finding.scan_source,
            detected_at=datetime.now(UTC),
            evidence_json={"summary": finding.evidence_summary},
            metadata_json=finding.metadata,
        )
        self.db.add(flag)
        self.db.flush()
        return flag
