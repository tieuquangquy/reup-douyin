from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.settings import Settings, get_settings
from src.enums import ExternalPublicationStatus, PlatformAccountStatus, PublishAttemptStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PlatformPublication, PublishAttempt


ACTIVE_FACEBOOK_ATTEMPT_STATUSES = frozenset(
    {
        PublishAttemptStatus.QUEUED,
        PublishAttemptStatus.RUNNING,
        PublishAttemptStatus.UPLOADING,
        PublishAttemptStatus.PUBLISHING,
        PublishAttemptStatus.AWAITING_PLATFORM_CONFIRMATION,
        PublishAttemptStatus.RECONCILING,
    }
)
FACEBOOK_RATE_LIMIT_ERRORS = frozenset({"facebook_rate_limited"})
FACEBOOK_HOLD_ERRORS = frozenset(
    {
        "facebook_auth_or_permission_denied",
        "facebook_platform_restriction",
        "facebook_token_invalid",
        "facebook_token_unavailable",
    }
)


@dataclass(frozen=True)
class FacebookPublishSafetyDecision:
    allowed: bool
    reasons: list[str]
    warnings: list[str]


class FacebookPublishSafetyService:
    """Fail-closed Page admission control without making a Meta request."""

    def __init__(self, db: Session, *, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def evaluate(
        self,
        account: PlatformAccount,
        *,
        current_attempt_id: UUID | None = None,
        now: datetime | None = None,
    ) -> FacebookPublishSafetyDecision:
        if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
            return FacebookPublishSafetyDecision(True, [], [])
        if not self.settings.facebook_publish_guardrails_enabled:
            return FacebookPublishSafetyDecision(
                True,
                [],
                ["Facebook Page publish guardrails are disabled by server configuration"],
            )

        current_time = now or datetime.now(UTC)
        reasons: list[str] = []
        warnings: list[str] = []
        metadata = account.metadata_json or {}

        if self.settings.facebook_publish_require_verified_capability:
            scopes = {
                str(value).strip()
                for value in (metadata.get("facebook_verified_publish_scopes") or [])
                if str(value).strip()
            }
            tasks = {
                str(value).strip().upper()
                for value in (metadata.get("facebook_page_tasks") or [])
                if str(value).strip()
            }
            verified_at = _parse_aware_datetime(
                metadata.get("facebook_publish_capability_verified_at")
            )
            max_age = timedelta(
                days=max(1, int(self.settings.facebook_publish_capability_max_age_days))
            )
            if metadata.get("facebook_publish_capability_verified") is not True:
                reasons.append("Facebook Page publish capability has not been verified through OAuth")
            if "pages_manage_posts" not in scopes:
                reasons.append("Facebook OAuth grant is missing pages_manage_posts")
            if "CREATE_CONTENT" not in tasks:
                reasons.append("Facebook Page tasks do not include CREATE_CONTENT")
            if verified_at is None or not (
                current_time - max_age <= verified_at <= current_time + timedelta(minutes=5)
            ):
                reasons.append("Facebook publish capability verification is stale; reconnect the Page")

        active_count = self._count_attempts(
            account.id,
            statuses=ACTIVE_FACEBOOK_ATTEMPT_STATUSES,
            current_attempt_id=current_attempt_id,
        )
        max_concurrent = max(
            1, int(self.settings.facebook_publish_max_concurrent_per_account)
        )
        if active_count >= max_concurrent:
            reasons.append("Another publish attempt is already active for this Facebook Page")

        unresolved_count = self._count_unresolved(
            account.id,
            current_attempt_id=current_attempt_id,
        )
        if unresolved_count:
            reasons.append(
                "A previous Facebook publish is unresolved; reconcile it before publishing again"
            )

        connected_at = _parse_aware_datetime(metadata.get("facebook_oauth_connected_at"))
        stage = self._stage_policy(account.id, connected_at=connected_at, now=current_time)
        min_interval_minutes = stage["min_interval_minutes"]
        max_attempts_24h = stage["max_attempts_24h"]
        if stage["name"] != "STANDARD":
            warnings.append(
                f"Facebook Page is in the {str(stage['name']).lower()} publishing stage"
            )

        last_attempt_at = self._latest_attempt_at(
            account.id,
            current_attempt_id=current_attempt_id,
        )
        if last_attempt_at is not None and last_attempt_at > current_time - timedelta(
            minutes=max(1, int(min_interval_minutes))
        ):
            reasons.append(
                f"Facebook Page minimum publish interval is {max(1, int(min_interval_minutes))} minutes"
            )

        attempts_24h = self._count_recent_attempts(
            account.id,
            since=current_time - timedelta(hours=24),
            current_attempt_id=current_attempt_id,
        )
        if attempts_24h >= max(1, int(max_attempts_24h)):
            reasons.append(
                f"Facebook Page reached the conservative 24-hour attempt budget ({max(1, int(max_attempts_24h))})"
            )

        failures_24h = self._count_recent_failures(
            account.id,
            since=current_time - timedelta(hours=24),
            current_attempt_id=current_attempt_id,
        )
        if failures_24h >= max(
            1, int(self.settings.facebook_publish_max_failures_per_24h)
        ):
            reasons.append("Facebook Page has too many recent publish failures; investigate before retrying")

        return FacebookPublishSafetyDecision(not reasons, reasons, warnings)

    def status(
        self,
        account: PlatformAccount,
        *,
        now: datetime | None = None,
    ) -> dict:
        """Return one secret-safe UI snapshot of effective Page safety state."""

        current_time = now or datetime.now(UTC)
        metadata = account.metadata_json or {}
        scopes = sorted(
            {
                str(value).strip()
                for value in (metadata.get("facebook_verified_publish_scopes") or [])
                if str(value).strip()
            }
        )
        tasks = sorted(
            {
                str(value).strip().upper()
                for value in (metadata.get("facebook_page_tasks") or [])
                if str(value).strip()
            }
        )
        connected_at = _parse_aware_datetime(metadata.get("facebook_oauth_connected_at"))
        capability_verified_at = _parse_aware_datetime(
            metadata.get("facebook_publish_capability_verified_at")
        )
        capability_max_age = timedelta(
            days=max(1, int(self.settings.facebook_publish_capability_max_age_days))
        )
        capability_expires_at = (
            capability_verified_at + capability_max_age
            if capability_verified_at
            else None
        )
        warmup_duration = timedelta(
            days=max(0, int(self.settings.facebook_publish_warmup_days))
        )
        warmup_until = connected_at + warmup_duration if connected_at else None
        stage = self._stage_policy(account.id, connected_at=connected_at, now=current_time)
        warmup = stage["name"] != "STANDARD"
        min_interval_minutes = int(stage["min_interval_minutes"])
        max_attempts_24h = int(stage["max_attempts_24h"])
        active_attempts = self._count_attempts(
            account.id,
            statuses=ACTIVE_FACEBOOK_ATTEMPT_STATUSES,
            current_attempt_id=None,
        )
        unresolved_attempts = self._count_unresolved(
            account.id,
            current_attempt_id=None,
        )
        last_attempt_at = self._latest_attempt_at(
            account.id,
            current_attempt_id=None,
        )
        attempts_24h = self._count_recent_attempts(
            account.id,
            since=current_time - timedelta(hours=24),
            current_attempt_id=None,
        )
        failures_24h = self._count_recent_failures(
            account.id,
            since=current_time - timedelta(hours=24),
            current_attempt_id=None,
        )
        next_publish_at = (
            last_attempt_at + timedelta(minutes=min_interval_minutes)
            if last_attempt_at
            else None
        )
        if next_publish_at and next_publish_at <= current_time:
            next_publish_at = None

        blocker_codes: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        def block(code: str, message: str) -> None:
            blocker_codes.append(code)
            blockers.append(message)

        if account.status != PlatformAccountStatus.ACTIVE:
            block("account_status", f"Account status is {account.status.value}")
        if account.is_on_hold:
            block("account_hold", account.hold_reason or "Account is on hold")
        cooldown_until = _as_aware(account.cooldown_until)
        if cooldown_until and cooldown_until > current_time:
            block("account_cooldown", "Account is in a safety cooldown window")

        if not self.settings.facebook_publish_guardrails_enabled:
            warnings.append("Facebook publish guardrails are disabled by server configuration")
        else:
            if self.settings.facebook_publish_require_verified_capability:
                if metadata.get("facebook_publish_capability_verified") is not True:
                    block("publish_capability", "Publish capability is not OAuth-verified")
                if "pages_manage_posts" not in scopes:
                    block("publish_scope", "OAuth grant is missing pages_manage_posts")
                if "CREATE_CONTENT" not in tasks:
                    block("publish_page_task", "Page tasks are missing CREATE_CONTENT")
                if capability_verified_at is None or not (
                    current_time - capability_max_age
                    <= capability_verified_at
                    <= current_time + timedelta(minutes=5)
                ):
                    block("publish_capability_fresh", "Publish capability is stale; reconnect the Page")
            if active_attempts >= max(
                1, int(self.settings.facebook_publish_max_concurrent_per_account)
            ):
                block("active_attempt", "Another publish attempt is active for this Page")
            if unresolved_attempts:
                block("unresolved_attempt", "A previous publish must be reconciled first")
            if next_publish_at:
                block("minimum_interval", "The Page is waiting for its minimum publish interval")
            if attempts_24h >= max_attempts_24h:
                block("attempt_budget", "The Page reached its conservative 24-hour attempt budget")
            if failures_24h >= max(
                1, int(self.settings.facebook_publish_max_failures_per_24h)
            ):
                block("failure_budget", "The Page has too many recent publish failures")
            if warmup:
                warnings.append(
                    f"Page is in the {str(stage['name']).lower()} publishing stage; promotion requires both elapsed time and confirmed connector publishes"
                )

        reconnect_codes = {
            "publish_capability",
            "publish_scope",
            "publish_page_task",
            "publish_capability_fresh",
        }
        cadence_codes = {"active_attempt", "minimum_interval", "attempt_budget"}
        if "account_hold" in blocker_codes:
            state = "HOLD"
        elif "account_cooldown" in blocker_codes:
            state = "COOLDOWN"
        elif reconnect_codes.intersection(blocker_codes):
            state = "RECONNECT_REQUIRED"
        elif set(blocker_codes).intersection(cadence_codes):
            state = "CADENCE_WAIT"
        elif blocker_codes:
            state = "BLOCKED"
        elif warmup:
            state = "WARM_UP"
        else:
            state = "READY"

        token_reference = str(account.token_reference or "")
        return {
            "platform_account_id": account.id,
            "state": state,
            "eligible_for_publish": not blocker_codes,
            "credential_source": str(metadata.get("credential_source") or "") or None,
            "managed_credential": token_reference.startswith("platform-credential://"),
            "hold_reason": account.hold_reason,
            "cooldown_until": cooldown_until,
            "connected_at": connected_at,
            "capability_verified_at": capability_verified_at,
            "capability_expires_at": capability_expires_at,
            "warmup_until": warmup_until,
            "next_publish_at": next_publish_at,
            "verified_publish_scopes": scopes,
            "page_tasks": tasks,
            "attempts_24h": attempts_24h,
            "failures_24h": failures_24h,
            "active_attempts": active_attempts,
            "unresolved_attempts": unresolved_attempts,
            "effective_min_interval_minutes": min_interval_minutes,
            "effective_max_attempts_24h": max_attempts_24h,
            "warmup_stage": stage["name"],
            "confirmed_connector_publishes": stage["confirmed_successes"],
            "next_stage_min_successes": stage["next_stage_min_successes"],
            "next_stage_earliest_at": stage["next_stage_earliest_at"],
            "blocker_codes": blocker_codes,
            "blockers": blockers,
            "warnings": warnings,
        }

    def apply_connector_failure(
        self,
        account: PlatformAccount,
        *,
        error_code: str,
        now: datetime | None = None,
    ) -> None:
        """Apply deterministic safety reactions without inspecting provider secrets."""

        if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
            return
        current_time = now or datetime.now(UTC)
        metadata = dict(account.metadata_json or {})
        metadata["facebook_publish_last_safety_error_code"] = error_code
        metadata["facebook_publish_last_safety_error_at"] = current_time.isoformat()
        account.metadata_json = metadata

        if error_code in FACEBOOK_RATE_LIMIT_ERRORS:
            proposed = current_time + timedelta(
                minutes=max(
                    1, int(self.settings.facebook_publish_rate_limit_cooldown_minutes)
                )
            )
            existing = _as_aware(account.cooldown_until)
            account.cooldown_until = max(existing, proposed) if existing else proposed
            return

        if error_code in FACEBOOK_HOLD_ERRORS:
            account.status = PlatformAccountStatus.PAUSED
            account.is_on_hold = True
            account.hold_reason = (
                "FACEBOOK_SAFETY_HOLD: Meta rejected the token, permission, or Page operation. "
                "Reconnect and verify the Page before resuming."
            )

    def _base_attempt_filters(
        self,
        account_id: UUID,
        *,
        current_attempt_id: UUID | None,
    ) -> list[object]:
        filters: list[object] = [PublishAttempt.platform_account_id == account_id]
        if current_attempt_id is not None:
            filters.append(PublishAttempt.id != current_attempt_id)
        return filters

    def _count_attempts(
        self,
        account_id: UUID,
        *,
        statuses: frozenset[PublishAttemptStatus],
        current_attempt_id: UUID | None,
    ) -> int:
        filters = self._base_attempt_filters(
            account_id,
            current_attempt_id=current_attempt_id,
        )
        filters.append(PublishAttempt.status.in_(statuses))
        return int(
            self.db.scalar(select(func.count(PublishAttempt.id)).where(*filters)) or 0
        )

    def _count_unresolved(
        self,
        account_id: UUID,
        *,
        current_attempt_id: UUID | None,
    ) -> int:
        filters = self._base_attempt_filters(
            account_id,
            current_attempt_id=current_attempt_id,
        )
        filters.append(PublishAttempt.reconciliation_required.is_(True))
        return int(
            self.db.scalar(select(func.count(PublishAttempt.id)).where(*filters)) or 0
        )

    def _latest_attempt_at(
        self,
        account_id: UUID,
        *,
        current_attempt_id: UUID | None,
    ) -> datetime | None:
        filters = self._base_attempt_filters(
            account_id,
            current_attempt_id=current_attempt_id,
        )
        value = self.db.scalar(
            select(PublishAttempt.created_at)
            .where(*filters)
            .order_by(PublishAttempt.created_at.desc())
            .limit(1)
        )
        return _as_aware(value)

    def _count_recent_attempts(
        self,
        account_id: UUID,
        *,
        since: datetime,
        current_attempt_id: UUID | None,
    ) -> int:
        filters = self._base_attempt_filters(
            account_id,
            current_attempt_id=current_attempt_id,
        )
        filters.extend(
            [
                PublishAttempt.created_at >= since,
                PublishAttempt.status != PublishAttemptStatus.CANCELLED,
            ]
        )
        return int(
            self.db.scalar(select(func.count(PublishAttempt.id)).where(*filters)) or 0
        )

    def _count_recent_failures(
        self,
        account_id: UUID,
        *,
        since: datetime,
        current_attempt_id: UUID | None,
    ) -> int:
        filters = self._base_attempt_filters(
            account_id,
            current_attempt_id=current_attempt_id,
        )
        filters.extend(
            [
                PublishAttempt.created_at >= since,
                PublishAttempt.status == PublishAttemptStatus.FAILED,
            ]
        )
        return int(
            self.db.scalar(select(func.count(PublishAttempt.id)).where(*filters)) or 0
        )

    def _stage_policy(
        self,
        account_id: UUID,
        *,
        connected_at: datetime | None,
        now: datetime,
    ) -> dict:
        confirmed = int(
            self.db.scalar(
                select(func.count(PlatformPublication.id)).where(
                    PlatformPublication.platform_account_id == account_id,
                    PlatformPublication.status == ExternalPublicationStatus.PUBLISHED,
                    PlatformPublication.origin == "CONNECTOR_PUBLISH",
                )
            )
            or 0
        )
        if connected_at is None:
            return {
                "name": "STANDARD",
                "confirmed_successes": confirmed,
                "min_interval_minutes": max(1, int(self.settings.facebook_publish_min_interval_minutes)),
                "max_attempts_24h": max(1, int(self.settings.facebook_publish_max_attempts_per_24h)),
                "next_stage_min_successes": None,
                "next_stage_earliest_at": None,
            }
        observe_at = connected_at + timedelta(
            hours=max(1, int(self.settings.facebook_publish_observe_min_age_hours))
        )
        standard_at = connected_at + timedelta(
            days=max(1, int(self.settings.facebook_publish_warmup_days))
        )
        observe_successes = max(1, int(self.settings.facebook_publish_observe_min_successes))
        standard_successes = max(
            observe_successes,
            int(self.settings.facebook_publish_standard_min_successes),
        )
        if now >= standard_at and confirmed >= standard_successes:
            return {
                "name": "STANDARD",
                "confirmed_successes": confirmed,
                "min_interval_minutes": max(1, int(self.settings.facebook_publish_min_interval_minutes)),
                "max_attempts_24h": max(1, int(self.settings.facebook_publish_max_attempts_per_24h)),
                "next_stage_min_successes": None,
                "next_stage_earliest_at": None,
            }
        if now >= observe_at and confirmed >= observe_successes:
            return {
                "name": "OBSERVE",
                "confirmed_successes": confirmed,
                "min_interval_minutes": max(1, int(self.settings.facebook_publish_observe_min_interval_minutes)),
                "max_attempts_24h": max(1, int(self.settings.facebook_publish_observe_max_attempts_per_24h)),
                "next_stage_min_successes": standard_successes,
                "next_stage_earliest_at": standard_at,
            }
        return {
            "name": "PILOT",
            "confirmed_successes": confirmed,
            "min_interval_minutes": max(1, int(self.settings.facebook_publish_warmup_min_interval_minutes)),
            "max_attempts_24h": max(1, int(self.settings.facebook_publish_warmup_max_attempts_per_24h)),
            "next_stage_min_successes": observe_successes,
            "next_stage_earliest_at": observe_at,
        }


def _parse_aware_datetime(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return _as_aware(value)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
