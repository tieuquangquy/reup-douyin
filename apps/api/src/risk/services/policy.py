from __future__ import annotations

from src.enums import OperatorRiskDecisionType, RiskFlagStatus, RiskSeverity
from src.risk.types import BLOCKING_SEVERITIES, RiskGateSummary


def evaluate_gate(flags: list[object], latest_decision: object | None = None) -> RiskGateSummary:
    accepted = getattr(latest_decision, "decision_type", None) == OperatorRiskDecisionType.ACCEPT_WITH_WARNING
    active = [
        flag for flag in flags
        if getattr(flag, "status", None) in {RiskFlagStatus.OPEN, RiskFlagStatus.ACKNOWLEDGED}
    ]
    counts: dict[str, int] = {}
    for flag in active:
        severity = str(getattr(flag, "severity", "UNKNOWN"))
        severity = severity.rsplit(".", 1)[-1]
        counts[severity] = counts.get(severity, 0) + 1
    highest = _highest([getattr(flag, "severity", None) for flag in active])
    blocking_flags = [flag for flag in active if getattr(flag, "severity", None) in BLOCKING_SEVERITIES]
    has_high = any(getattr(flag, "severity", None) == RiskSeverity.HIGH for flag in active)
    can_continue = not blocking_flags or accepted
    return RiskGateSummary(
        can_continue=can_continue,
        requires_operator_decision=bool(blocking_flags or has_high),
        blocking_reasons=[getattr(flag, "title", None) or str(getattr(flag, "flag_type", "risk")) for flag in blocking_flags],
        highest_severity=highest,
        open_counts_by_severity=counts,
        accepted_with_warning=accepted,
    )


def _highest(severities: list[RiskSeverity | None]) -> RiskSeverity | None:
    order = {
        RiskSeverity.LOW: 1,
        RiskSeverity.MEDIUM: 2,
        RiskSeverity.HIGH: 3,
        RiskSeverity.CRITICAL: 4,
        RiskSeverity.BLOCKING: 4,
    }
    ranked = [severity for severity in severities if severity in order]
    return max(ranked, key=lambda item: order[item]) if ranked else None
