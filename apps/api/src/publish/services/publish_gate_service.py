from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from src.enums import PlatformAccountStatus, PublishDraftStatus, PublishTargetPlatform, RenderOutputStatus, RiskTargetType, SourceVideoStatus
from src.models.ingestion import SourceVideo
from src.models.media import RenderOutput
from src.models.publish import PlatformAccount, PublishDraft
from src.publish.services.facebook_publish_safety_service import FacebookPublishSafetyService
from src.publish.types import PublishGateResult
from src.risk.services.risk_service import RiskService


class PublishGateService:
    def __init__(self, db: Session):
        self.db = db

    def evaluate(
        self,
        draft: PublishDraft,
        render: RenderOutput | None,
        account: PlatformAccount | None,
        *,
        allowed_draft_statuses: frozenset[PublishDraftStatus] | None = None,
        current_attempt_id: UUID | None = None,
    ) -> PublishGateResult:
        reasons: list[str] = []
        warnings: list[str] = []
        source_video = self.db.get(SourceVideo, draft.source_video_id)
        allowed_statuses = allowed_draft_statuses or frozenset({PublishDraftStatus.READY})
        if draft.status not in allowed_statuses:
            reasons.append(
                "Publish draft must be one of "
                + ", ".join(sorted(status.value for status in allowed_statuses))
                + " before publishing"
            )
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
            if account.is_on_hold:
                reasons.append("Platform account is on hold")
            if account.cooldown_until is not None:
                cooldown_until = account.cooldown_until
                if cooldown_until.tzinfo is None or cooldown_until.utcoffset() is None:
                    cooldown_until = cooldown_until.replace(tzinfo=UTC)
                if cooldown_until > datetime.now(UTC):
                    reasons.append("Platform account is in a safety cooldown window")
            facebook_safety = FacebookPublishSafetyService(self.db).evaluate(
                account,
                current_attempt_id=current_attempt_id,
            )
            reasons.extend(facebook_safety.reasons)
            warnings.extend(facebook_safety.warnings)

        risk_gate = RiskService(self.db).gate_summary(RiskTargetType.PUBLISH_DRAFT, draft.id)
        if not risk_gate.can_continue:
            reasons.extend(risk_gate.blocking_reasons or ["Risk gate blocked publish"])
        if risk_gate.requires_operator_decision:
            warnings.append("Risk gate requires an explicit operator decision")

        return PublishGateResult(allowed=not reasons, reasons=reasons, warnings=warnings)
