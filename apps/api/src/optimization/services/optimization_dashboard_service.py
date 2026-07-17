from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PublishDraftStatus
from src.models.publish import PublishDraft
from src.optimization.services.optimization_signal_service import OptimizationSignalService
from src.optimization.services.outcome_score_service import OutcomeScoreService
from src.optimization.services.routing_hint_service import RoutingHintService
from src.schemas.optimization import OptimizationDashboardResponse


class OptimizationDashboardService:
    def __init__(self, db: Session):
        self.db = db
        self.outcome_service = OutcomeScoreService(db)
        self.signal_service = OptimizationSignalService(db)
        self.routing_hint_service = RoutingHintService(db)

    def snapshot(self) -> OptimizationDashboardResponse:
        ready_drafts = list(
            self.db.scalars(
                select(PublishDraft)
                .where(PublishDraft.status == PublishDraftStatus.READY)
                .order_by(PublishDraft.updated_at.desc())
                .limit(5)
            )
        )
        hints = []
        for draft in ready_drafts:
            try:
                hints.append(self.routing_hint_service.routing_hints(draft.id))
            except Exception:
                continue
        return OptimizationDashboardResponse(
            generated_at=datetime.now(UTC),
            outcome_summaries=self.outcome_service.outcome_summaries(),
            preset_feedback=self.signal_service.preset_feedback(),
            manual_touch_summary=self.signal_service.manual_touch_summary(),
            ready_draft_routing_hints=hints,
        )

