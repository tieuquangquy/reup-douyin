from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PublishRoutingRuleStatus, PublishTargetPlatform
from src.models.publish import PublishDraft, PublishRoutingRule
from src.schemas.publish_routing import PublishRoutingRuleCreateRequest, PublishRoutingRuleUpdateRequest


class RoutingRuleError(ValueError):
    pass


class RoutingRuleService:
    def __init__(self, db: Session):
        self.db = db

    def list_rules(self, *, platform: PublishTargetPlatform | None = None, include_archived: bool = False) -> list[PublishRoutingRule]:
        stmt = select(PublishRoutingRule).order_by(PublishRoutingRule.priority.desc(), PublishRoutingRule.created_at.asc())
        if platform is not None:
            stmt = stmt.where(PublishRoutingRule.platform == platform)
        if not include_archived:
            stmt = stmt.where(PublishRoutingRule.status != PublishRoutingRuleStatus.ARCHIVED)
        return list(self.db.scalars(stmt))

    def create_rule(self, request: PublishRoutingRuleCreateRequest) -> PublishRoutingRule:
        rule = PublishRoutingRule(
            workspace_id=request.workspace_id,
            platform=request.platform,
            rule_name=request.rule_name,
            status=request.status,
            priority=request.priority,
            match_json=request.match_json,
            action_json=request.action_json,
            fallback_behavior=request.fallback_behavior,
            metadata_json=request.metadata_json,
            notes=request.notes,
        )
        self.db.add(rule)
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def update_rule(self, rule_id: UUID, request: PublishRoutingRuleUpdateRequest) -> PublishRoutingRule:
        rule = self.db.get(PublishRoutingRule, rule_id)
        if rule is None:
            raise RoutingRuleError("Routing rule not found")
        for field in request.model_fields_set:
            setattr(rule, field, getattr(request, field))
        self.db.commit()
        self.db.refresh(rule)
        return rule

    def matching_rules(self, draft: PublishDraft) -> list[PublishRoutingRule]:
        rules = self.list_rules(platform=PublishTargetPlatform(draft.target_platform))
        return [rule for rule in rules if rule.status == PublishRoutingRuleStatus.ACTIVE and self._matches(rule, draft)]

    def _matches(self, rule: PublishRoutingRule, draft: PublishDraft) -> bool:
        match = rule.match_json or {}
        if not match:
            return True
        for key, expected in match.items():
            actual = self._draft_value(draft, key)
            if expected is None:
                continue
            if isinstance(expected, list):
                if actual not in {str(item) for item in expected}:
                    return False
            elif str(actual) != str(expected):
                return False
        return True

    def _draft_value(self, draft: PublishDraft, key: str) -> str | None:
        payloads = [draft.metadata_json or {}, draft.platform_payload_json or {}, draft.caption_draft_json or {}]
        if key in {"source_video_id", "sourceVideoId"}:
            return str(draft.source_video_id)
        if key in {"preset", "preset_name"}:
            for payload in payloads:
                value = payload.get("preset") or payload.get("preset_name")
                if value:
                    return str(value)
        if key in {"niche", "niche_tag", "niche_label"}:
            for payload in payloads:
                value = payload.get("niche") or payload.get("niche_tag") or payload.get("niche_label")
                if value:
                    return str(value)
        for payload in payloads:
            value = payload.get(key)
            if value:
                return str(value)
        return None

