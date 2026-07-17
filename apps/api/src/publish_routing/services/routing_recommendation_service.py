from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PublishTargetPlatform
from src.models.publish import PlatformAccount, PublishDraft, PublishRoutingRule
from src.publish_routing.services.account_eligibility_service import AccountEligibilityService
from src.publish_routing.services.account_health_service import AccountHealthService
from src.publish_routing.services.routing_rule_service import RoutingRuleService
from src.publish_routing.types import AccountEligibility
from src.schemas.publish_routing import RoutingRecommendationResponse


class RoutingRecommendationError(ValueError):
    pass


class RoutingRecommendationService:
    def __init__(self, db: Session):
        self.db = db
        self.health_service = AccountHealthService(db)
        self.eligibility_service = AccountEligibilityService()
        self.rule_service = RoutingRuleService(db)

    def recommend_for_draft(self, publish_draft_id: UUID) -> RoutingRecommendationResponse:
        draft = self.db.get(PublishDraft, publish_draft_id)
        if draft is None:
            raise RoutingRecommendationError("Publish draft not found")
        accounts = list(
            self.db.scalars(
                select(PlatformAccount)
                .where(PlatformAccount.workspace_id == draft.workspace_id, PlatformAccount.platform == PublishTargetPlatform(draft.target_platform))
                .order_by(PlatformAccount.priority.desc(), PlatformAccount.display_name.asc())
            )
        )
        health_by_id = {item.platform_account_id: item for item in self.health_service.list_account_health()}
        matched_rules = self.rule_service.matching_rules(draft)
        recommended_ids, excluded_ids, rule_warnings = self._rule_actions(matched_rules)

        eligible: list[AccountEligibility] = []
        blocked: list[AccountEligibility] = []
        for account in accounts:
            health = health_by_id.get(account.id) or self.health_service.account_health(account)
            evaluation = self.eligibility_service.evaluate(draft=draft, account=account, health=health)
            score = evaluation.score
            reasons = list(evaluation.recommendation_reasons)
            blocking = list(evaluation.blocking_reasons)
            warnings = list(evaluation.warnings)
            if account.id in excluded_ids:
                blocking.append("Excluded by routing rule")
            if account.id in recommended_ids:
                score += 50
                reasons.append("Matched routing rule recommendation")
            patched = AccountEligibility(
                platform_account_id=evaluation.platform_account_id,
                display_name=evaluation.display_name,
                eligible=evaluation.eligible and not blocking,
                health_status=evaluation.health_status,
                score=score,
                blocking_reasons=blocking,
                warnings=warnings,
                recommendation_reasons=reasons,
            )
            (eligible if patched.eligible else blocked).append(patched)

        eligible.sort(key=lambda item: item.score, reverse=True)
        blocked.sort(key=lambda item: item.display_name)
        return RoutingRecommendationResponse(
            publish_draft_id=draft.id,
            matched_rule_ids=[rule.id for rule in matched_rules],
            matched_rule_names=[rule.rule_name for rule in matched_rules],
            recommended_accounts=eligible,
            blocked_accounts=blocked,
            warnings=rule_warnings,
        )

    def _rule_actions(self, rules: list[PublishRoutingRule]) -> tuple[set[UUID], set[UUID], list[str]]:
        recommended: set[UUID] = set()
        excluded: set[UUID] = set()
        warnings: list[str] = []
        for rule in rules:
            action = rule.action_json or {}
            for raw_id in action.get("recommend_account_ids", []) or []:
                parsed = self._parse_uuid(raw_id)
                if parsed:
                    recommended.add(parsed)
                else:
                    warnings.append(f"Rule '{rule.rule_name}' has an invalid recommended account id")
            for raw_id in action.get("exclude_account_ids", []) or []:
                parsed = self._parse_uuid(raw_id)
                if parsed:
                    excluded.add(parsed)
                else:
                    warnings.append(f"Rule '{rule.rule_name}' has an invalid excluded account id")
            if action.get("require_manual_review"):
                warnings.append(f"Rule '{rule.rule_name}' requires manual account review")
        return recommended, excluded, warnings

    def _parse_uuid(self, value: object) -> UUID | None:
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None
