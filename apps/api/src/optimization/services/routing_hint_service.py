from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import RiskTargetType
from src.models.publish import PublishDraft
from src.models.review import RiskFlag
from src.optimization.services.automation_policy_service import AutomationPolicyService
from src.optimization.services.outcome_score_service import OutcomeScoreService
from src.publish_routing.services.routing_recommendation_service import RoutingRecommendationService
from src.schemas.optimization import RoutingHintAccount, RoutingHintsResponse, SchedulingHintsResponse, SchedulingSlotHint


class RoutingHintError(ValueError):
    pass


class RoutingHintService:
    def __init__(self, db: Session):
        self.db = db
        self.routing_service = RoutingRecommendationService(db)
        self.outcome_service = OutcomeScoreService(db)
        self.policy_service = AutomationPolicyService()

    def routing_hints(self, publish_draft_id: UUID) -> RoutingHintsResponse:
        draft = self._draft(publish_draft_id)
        recommendation = self.routing_service.recommend_for_draft(publish_draft_id)
        context_score, context_reason = self._routing_context_score(draft)
        boosted = []
        for account in recommendation.recommended_accounts:
            normalized_account_score = self._normalize_account_score(account.score)
            score = min(100.0, max(0.0, (normalized_account_score * 0.65) + (context_score * 0.35)))
            confidence = self._confidence(score)
            reasons = list(account.recommendation_reasons) + [context_reason]
            if context_score >= 80:
                reasons.append("Outcome context is strong enough to increase routing confidence.")
            elif context_score < 55:
                reasons.append("Outcome context is weak; keep manual review.")
            boosted.append(
                RoutingHintAccount(
                    platform_account_id=account.platform_account_id,
                    display_name=account.display_name,
                    confidence_score=round(score, 2),
                    confidence_label=confidence,
                    health_status=account.health_status.value,
                    reasons=reasons,
                    warnings=account.warnings,
                )
            )
        blocked = [
            RoutingHintAccount(
                platform_account_id=account.platform_account_id,
                display_name=account.display_name,
                confidence_score=0,
                confidence_label="blocked",
                health_status=account.health_status.value,
                reasons=account.blocking_reasons,
                warnings=account.warnings,
            )
            for account in recommendation.blocked_accounts
        ]
        boosted.sort(key=lambda item: item.confidence_score, reverse=True)
        policy = self.policy_service.evaluate_auto_assign(draft=draft, top_hint=boosted[0] if boosted else None, risk_flags=self._risk_flags(draft))
        return RoutingHintsResponse(
            publish_draft_id=publish_draft_id,
            recommended_accounts=boosted,
            blocked_accounts=blocked,
            automation_policy=policy,
            explanation=[
                "Routing uses account health, routing rules, current backlog, and outcome context.",
                "Operator override remains available; auto-assign is only allowed when guardrails pass.",
            ],
        )

    def scheduling_hints(self, publish_draft_id: UUID) -> SchedulingHintsResponse:
        draft = self._draft(publish_draft_id)
        hints = self.routing_hints(publish_draft_id)
        now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
        top_accounts = hints.recommended_accounts[:3]
        slots: list[SchedulingSlotHint] = []
        for index, account in enumerate(top_accounts or []):
            candidate_time = now + timedelta(hours=2 + (index * 2))
            confidence = "high" if account.confidence_label == "high" and index == 0 else "medium"
            warnings = list(account.warnings)
            if account.confidence_label != "high":
                warnings.append("Account routing confidence is not high.")
            slots.append(
                SchedulingSlotHint(
                    platform_account_id=account.platform_account_id,
                    account_name=account.display_name,
                    suggested_publish_at=candidate_time,
                    confidence_label=confidence,
                    reasons=[
                        "Simple phase 1 slot spacing avoids immediate backlog spikes.",
                        f"Account routing confidence is {account.confidence_label}.",
                    ],
                    warnings=warnings,
                )
            )
        if not slots:
            slots.append(
                SchedulingSlotHint(
                    suggested_publish_at=now + timedelta(hours=2),
                    confidence_label="low",
                    reasons=["No eligible account recommendation; operator must choose account first."],
                    warnings=["Manual scheduling required."],
                )
            )
        top_slot = slots[0]
        policy = self.policy_service.evaluate_auto_schedule(draft=draft, confidence_label=top_slot.confidence_label, warnings=top_slot.warnings)
        return SchedulingHintsResponse(
            publish_draft_id=publish_draft_id,
            suggested_slots=slots,
            automation_policy=policy,
            explanation=[
                "Scheduling hints are spacing suggestions, not an autopublish scheduler.",
                "Manual override remains the default for phase 1.",
            ],
        )

    def _draft(self, publish_draft_id: UUID) -> PublishDraft:
        draft = self.db.get(PublishDraft, publish_draft_id)
        if draft is None:
            raise RoutingHintError("Publish draft not found")
        return draft

    def _risk_flags(self, draft: PublishDraft) -> list[RiskFlag]:
        return list(
            self.db.scalars(
                select(RiskFlag).where(
                    (RiskFlag.target_type == RiskTargetType.PUBLISH_DRAFT) & (RiskFlag.target_id == draft.id)
                    | (RiskFlag.source_video_id == draft.source_video_id)
                )
            )
        )

    def _confidence(self, score: float) -> str:
        if score >= 80:
            return "high"
        if score >= 60:
            return "medium"
        return "low"

    def _routing_context_score(self, draft: PublishDraft) -> tuple[float, str]:
        if draft.latest_publish_attempt_id or draft.canonical_publish_attempt_id:
            outcome = self.outcome_service.score_for_draft(draft.id)
            return outcome.total_outcome_score, f"Uses this draft's post-publish outcome score {outcome.total_outcome_score}."
        if draft.status.value in {"PUBLISHED", "FAILED", "NEEDS_ATTENTION"}:
            outcome = self.outcome_service.score_for_draft(draft.id)
            return outcome.total_outcome_score, f"Uses this draft's terminal outcome score {outcome.total_outcome_score}."
        return 65.0, "Draft has no post-publish outcome yet; using neutral pre-publish context."

    def _normalize_account_score(self, score: int) -> float:
        return max(0.0, min(100.0, round(score / 1.5, 2)))
