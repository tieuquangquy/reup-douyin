from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.enums import PlatformAccountHealthStatus, PlatformAccountStatus, PublishTargetPlatform


@dataclass(frozen=True)
class AccountHealthStats:
    platform_account_id: UUID
    display_name: str
    platform: PublishTargetPlatform
    account_status: PlatformAccountStatus
    health_status: PlatformAccountHealthStatus
    priority: int
    is_on_hold: bool
    cooldown_until: datetime | None
    attempts_7d: int = 0
    succeeded_7d: int = 0
    failed_7d: int = 0
    needs_reconciliation_count: int = 0
    assigned_draft_count: int = 0
    scheduled_draft_count: int = 0
    recent_error_code: str | None = None
    success_rate_percent: float = 0.0
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AccountEligibility:
    platform_account_id: UUID
    display_name: str
    eligible: bool
    health_status: PlatformAccountHealthStatus
    score: int
    blocking_reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    recommendation_reasons: list[str] = field(default_factory=list)

