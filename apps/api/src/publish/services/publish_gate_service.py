from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from src.enums import PlatformAccountStatus, PublishDraftStatus, PublishTargetPlatform, RenderOutputStatus, RiskTargetType, SourceVideoStatus
from src.models.ingestion import SourceVideo
from src.models.media import RenderOutput
from src.models.publish import PlatformAccount, PublishDraft
from src.publish.types import PublishGateResult
from src.risk.services.risk_service import RiskService


class PublishGateService:
    def __init__(self, db: Session):
        self.db = db

    def evaluate(self, draft: PublishDraft, render: RenderOutput | None, account: PlatformAccount | None) -> PublishGateResult:
        reasons: list[str] = []
        warnings: list[str] = []
        source_video = self.db.get(SourceVideo, draft.source_video_id)
        if draft.status != PublishDraftStatus.READY:
            reasons.append("Publish draft must be READY before publishing")
        if draft.target_platform != PublishTargetPlatform.FACEBOOK_REELS.value:
            reasons.append("Step 18 only supports FACEBOOK_REELS")
        if source_video is None:
            reasons.append("Source video not found")
        elif source_video.status != SourceVideoStatus.PUBLISH_READY:
            reasons.append("Source video must be PUBLISH_READY")
        if render is None:
            reasons.append("Approved render output is required")
        elif render.status != RenderOutputStatus.APPROVED:
            reasons.append("Render output must be APPROVED")
        elif render.media_asset_id is None:
            reasons.append("Render output must reference a final media asset")
        if account is None:
            reasons.append("Platform account is required")
        else:
            if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
                reasons.append("Platform account must be FACEBOOK_REELS")
            if account.status != PlatformAccountStatus.ACTIVE:
                reasons.append("Platform account must be ACTIVE")

        risk_gate = RiskService(self.db).gate_summary(RiskTargetType.PUBLISH_DRAFT, draft.id)
        if not risk_gate.can_continue:
            reasons.extend(risk_gate.blocking_reasons or ["Risk gate blocked publish"])
        if risk_gate.requires_operator_decision:
            warnings.append("Risk gate requires an explicit operator decision")

        return PublishGateResult(allowed=not reasons, reasons=reasons, warnings=warnings)

