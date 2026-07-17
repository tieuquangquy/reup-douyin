from __future__ import annotations

from datetime import UTC, datetime

from src.enums import PlatformAccountHealthStatus, PlatformAccountStatus


def percent(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 2)


def classify_account_health(
    *,
    account_status: PlatformAccountStatus,
    is_on_hold: bool,
    cooldown_until: datetime | None,
    attempts_7d: int,
    success_rate_percent: float,
    failed_7d: int,
    needs_reconciliation_count: int,
) -> tuple[PlatformAccountHealthStatus, list[str]]:
    now = datetime.now(UTC)
    reasons: list[str] = []
    if account_status != PlatformAccountStatus.ACTIVE:
        reasons.append(f"Account status is {account_status.value}")
    if is_on_hold:
        reasons.append("Account is on manual hold")
    if cooldown_until and cooldown_until > now:
        reasons.append("Account is in cooldown window")
    if reasons:
        return PlatformAccountHealthStatus.HELD, reasons

    if needs_reconciliation_count >= 3:
        return PlatformAccountHealthStatus.UNHEALTHY, ["Too many attempts need reconciliation"]
    if failed_7d >= 3:
        return PlatformAccountHealthStatus.UNHEALTHY, ["Too many recent publish failures"]
    if attempts_7d >= 3 and success_rate_percent < 50:
        return PlatformAccountHealthStatus.UNHEALTHY, ["Recent success rate is below 50%"]

    if needs_reconciliation_count > 0:
        return PlatformAccountHealthStatus.DEGRADED, ["Some attempts need reconciliation"]
    if failed_7d > 0:
        return PlatformAccountHealthStatus.DEGRADED, ["Recent failures detected"]
    if attempts_7d >= 3 and success_rate_percent < 80:
        return PlatformAccountHealthStatus.DEGRADED, ["Recent success rate is below 80%"]

    return PlatformAccountHealthStatus.HEALTHY, ["No recent account health blockers"]


def health_score_boost(status: PlatformAccountHealthStatus) -> int:
    return {
        PlatformAccountHealthStatus.HEALTHY: 30,
        PlatformAccountHealthStatus.DEGRADED: 5,
        PlatformAccountHealthStatus.UNHEALTHY: -1000,
        PlatformAccountHealthStatus.HELD: -1000,
    }[status]

