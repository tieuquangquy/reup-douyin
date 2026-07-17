from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PublishDraftStatus, PublishTargetPlatform
from src.models.publish import PublishDraft
from src.publish_routing.services.account_health_service import AccountHealthService
from src.publish_routing.services.routing_recommendation_service import RoutingRecommendationService
from src.schemas.publish_routing import PublishControlQueueResponse, PublishDraftQueueItem


class ControlQueueService:
    def __init__(self, db: Session):
        self.db = db
        self.health_service = AccountHealthService(db)
        self.recommendation_service = RoutingRecommendationService(db)

    def queue(self, *, platform: PublishTargetPlatform = PublishTargetPlatform.FACEBOOK_REELS, limit: int = 100) -> PublishControlQueueResponse:
        drafts = list(
            self.db.scalars(
                select(PublishDraft)
                .where(PublishDraft.target_platform == platform.value)
                .order_by(PublishDraft.updated_at.desc())
                .limit(limit)
            )
        )
        items = [self._item(draft) for draft in drafts]
        return PublishControlQueueResponse(
            generated_at=datetime.now(UTC),
            accounts=self.health_service.list_account_health(platform=platform),
            unassigned_drafts=[item for item in items if item.status == PublishDraftStatus.READY and item.assigned_platform_account_id is None],
            assigned_drafts=[item for item in items if item.status == PublishDraftStatus.READY and item.assigned_platform_account_id is not None],
            scheduled_drafts=[item for item in items if item.status == PublishDraftStatus.SCHEDULED],
            needs_attention=[item for item in items if item.status in {PublishDraftStatus.NEEDS_ATTENTION, PublishDraftStatus.FAILED}],
        )

    def _item(self, draft: PublishDraft) -> PublishDraftQueueItem:
        try:
            recommendation = self.recommendation_service.recommend_for_draft(draft.id)
            recommended = recommendation.recommended_accounts[0] if recommendation.recommended_accounts else None
            warnings = recommendation.warnings + (recommended.warnings if recommended else [])
            reasons = recommended.recommendation_reasons if recommended else []
        except Exception as exc:  # keep queue readable even if one draft has incomplete data
            recommended = None
            warnings = [f"Could not compute recommendation: {exc}"]
            reasons = []
        return PublishDraftQueueItem(
            publish_draft_id=draft.id,
            source_video_id=draft.source_video_id,
            title=draft.title,
            status=draft.status,
            target_platform=draft.target_platform,
            planned_publish_at=draft.planned_publish_at,
            assigned_platform_account_id=draft.assigned_platform_account_id,
            assignment_status=draft.assignment_status,
            assigned_reason=draft.assigned_reason,
            recommended_platform_account_id=recommended.platform_account_id if recommended else None,
            recommended_account_name=recommended.display_name if recommended else None,
            recommendation_reasons=reasons,
            warnings=warnings,
        )

