from __future__ import annotations

from src.enums import PlatformAccountHealthStatus, PublishDraftStatus, RiskFlagStatus, RiskSeverity
from src.models.publish import PublishDraft
from src.models.review import RiskFlag
from src.schemas.optimization import RoutingHintAccount


class AutomationPolicyService:
    def evaluate_auto_assign(self, *, draft: PublishDraft, top_hint: RoutingHintAccount | None, risk_flags: list[RiskFlag]) -> dict:
        blocking_reasons: list[str] = []
        warnings: list[str] = []
        if draft.status != PublishDraftStatus.READY:
            blocking_reasons.append("Draft is not READY.")
        if top_hint is None:
            blocking_reasons.append("No eligible account recommendation.")
        elif top_hint.confidence_label != "high":
            blocking_reasons.append("Routing confidence is not high enough for auto-assign.")
        if top_hint and top_hint.health_status != PlatformAccountHealthStatus.HEALTHY.value:
            blocking_reasons.append("Recommended account is not healthy.")
        high_risk = [
            flag
            for flag in risk_flags
            if flag.status == RiskFlagStatus.OPEN and flag.severity in {RiskSeverity.HIGH, RiskSeverity.CRITICAL, RiskSeverity.BLOCKING}
        ]
        if high_risk:
            blocking_reasons.append("Open high or blocking risk warnings require manual review.")
        if draft.assignment_status and draft.assignment_status.value == "OVERRIDDEN":
            warnings.append("Draft has a previous manual override; keep operator control.")
        return {
            "can_auto_assign": not blocking_reasons,
            "requires_manual_review": bool(blocking_reasons),
            "blocking_reasons": blocking_reasons,
            "warnings": warnings,
            "policy": "phase1_guarded_semi_automation",
        }

    def evaluate_auto_schedule(self, *, draft: PublishDraft, confidence_label: str, warnings: list[str]) -> dict:
        blocking_reasons: list[str] = []
        if draft.status not in {PublishDraftStatus.READY, PublishDraftStatus.SCHEDULED}:
            blocking_reasons.append("Draft must be READY or SCHEDULED.")
        if not draft.assigned_platform_account_id:
            blocking_reasons.append("Draft must have an assigned account before auto-schedule.")
        if confidence_label != "high":
            blocking_reasons.append("Schedule confidence is not high enough for auto-fill.")
        if warnings:
            blocking_reasons.append("Schedule hint has warnings.")
        return {
            "can_auto_fill_schedule": not blocking_reasons,
            "requires_manual_review": bool(blocking_reasons),
            "blocking_reasons": blocking_reasons,
            "policy": "phase1_schedule_suggestion_only",
        }

