from __future__ import annotations

from src.enums import PlatformAccountHealthStatus, PlatformAccountStatus
from src.models.publish import PlatformAccount, PublishDraft
from src.publish_routing.services.routing_helpers import health_score_boost
from src.publish_routing.types import AccountEligibility, AccountHealthStats


class AccountEligibilityService:
    def evaluate(self, *, draft: PublishDraft, account: PlatformAccount, health: AccountHealthStats) -> AccountEligibility:
        blocking: list[str] = []
        warnings: list[str] = []
        reasons: list[str] = []

        if str(account.platform.value) != str(draft.target_platform):
            blocking.append("Account platform does not match publish draft target platform")
        if account.status != PlatformAccountStatus.ACTIVE:
            blocking.append(f"Account status is {account.status.value}")
        if account.is_on_hold:
            blocking.append("Account is on manual hold")
        if health.health_status in {PlatformAccountHealthStatus.HELD, PlatformAccountHealthStatus.UNHEALTHY}:
            blocking.extend([reason for reason in health.reasons if reason not in blocking])
        if not account.token_reference:
            warnings.append("Account token reference is missing")
        if health.health_status == PlatformAccountHealthStatus.DEGRADED:
            warnings.extend(health.reasons)
        if account.allowed_niches_json:
            draft_niche = self._draft_niche(draft)
            allowed = {str(item).lower() for item in account.allowed_niches_json}
            if draft_niche and draft_niche.lower() not in allowed:
                blocking.append(f"Draft niche '{draft_niche}' is not allowed for this account")

        score = account.priority + health_score_boost(health.health_status) - (health.assigned_draft_count * 2) - (health.needs_reconciliation_count * 5)
        if not blocking:
            reasons.append("Account is eligible for this draft")
        return AccountEligibility(
            platform_account_id=account.id,
            display_name=account.display_name,
            eligible=not blocking,
            health_status=health.health_status,
            score=score,
            blocking_reasons=blocking,
            warnings=warnings,
            recommendation_reasons=reasons,
        )

    def _draft_niche(self, draft: PublishDraft) -> str | None:
        for payload in [draft.metadata_json, draft.platform_payload_json]:
            if isinstance(payload, dict):
                value = payload.get("niche") or payload.get("niche_tag") or payload.get("niche_label")
                if value:
                    return str(value)
        return None

