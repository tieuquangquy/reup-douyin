from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta


CADENCE_POLICY_VERSION = "METRICS_CADENCE_V2"


@dataclass(frozen=True)
class CadenceDecision:
    status: str
    next_collection_at: datetime | None
    interval_seconds: int | None
    reason: str
    policy_version: str = CADENCE_POLICY_VERSION

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "next_collection_at": self.next_collection_at.isoformat() if self.next_collection_at else None,
            "interval_seconds": self.interval_seconds,
            "reason": self.reason,
            "policy_version": self.policy_version,
        }


def decide_next_collection(
    *,
    reference_at: datetime,
    published_at: datetime,
    trend_label: str,
    consecutive_flat_count: int,
    max_age_hours: int,
) -> CadenceDecision:
    age_hours = max(0.0, (reference_at - published_at).total_seconds() / 3600)
    if age_hours >= max(1, int(max_age_hours)):
        return CadenceDecision(
            status="COMPLETED",
            next_collection_at=None,
            interval_seconds=None,
            reason="publication_age_limit_reached",
        )

    if age_hours < 6:
        base_seconds = 3600
        age_band = "first_6h"
    elif age_hours < 24:
        base_seconds = 3 * 3600
        age_band = "first_24h"
    elif age_hours < 72:
        base_seconds = 12 * 3600
        age_band = "first_72h"
    else:
        base_seconds = 24 * 3600
        age_band = "long_tail"

    trend = str(trend_label or "INSUFFICIENT_DATA").upper()
    if trend in {"NO_DATA", "BASELINE_ONLY", "INSUFFICIENT_DATA"} and age_hours < 6:
        interval_seconds = 30 * 60
        reason = f"{age_band}:baseline_followup"
    elif trend == "GROWING":
        interval_seconds = max(30 * 60, base_seconds // 2)
        reason = f"{age_band}:growing_priority"
    elif trend == "FLAT":
        multiplier = min(4, 2 ** max(1, int(consecutive_flat_count)))
        interval_seconds = min(48 * 3600, base_seconds * multiplier)
        reason = f"{age_band}:flat_backoff_x{multiplier}"
    elif trend == "COUNTER_REGRESSION":
        interval_seconds = min(base_seconds, 3 * 3600)
        reason = f"{age_band}:counter_regression_recheck"
    else:
        interval_seconds = base_seconds
        reason = f"{age_band}:baseline"

    return CadenceDecision(
        status="ACTIVE",
        next_collection_at=reference_at + timedelta(seconds=interval_seconds),
        interval_seconds=interval_seconds,
        reason=reason,
    )
