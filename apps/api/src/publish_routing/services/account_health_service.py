from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishDraftStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PublishAttempt, PublishDraft
from src.publish_routing.services.routing_helpers import classify_account_health, percent
from src.publish_routing.types import AccountHealthStats


class AccountHealthService:
    def __init__(self, db: Session):
        self.db = db

    def list_account_health(self, platform: PublishTargetPlatform | None = None) -> list[AccountHealthStats]:
        accounts = list(self.db.scalars(self._account_query(platform)))
        attempts = self._recent_attempts()
        drafts = self._active_drafts()
        attempts_by_account: dict[UUID, list[PublishAttempt]] = defaultdict(list)
        drafts_by_account: dict[UUID, list[PublishDraft]] = defaultdict(list)
        for attempt in attempts:
            attempts_by_account[attempt.platform_account_id].append(attempt)
        for draft in drafts:
            if draft.assigned_platform_account_id:
                drafts_by_account[draft.assigned_platform_account_id].append(draft)
        return [self._build_stats(account, attempts_by_account.get(account.id, []), drafts_by_account.get(account.id, [])) for account in accounts]

    def account_health(self, account: PlatformAccount) -> AccountHealthStats:
        attempts = [item for item in self._recent_attempts() if item.platform_account_id == account.id]
        drafts = [item for item in self._active_drafts() if item.assigned_platform_account_id == account.id]
        return self._build_stats(account, attempts, drafts)

    def _account_query(self, platform: PublishTargetPlatform | None):
        stmt = select(PlatformAccount).order_by(PlatformAccount.priority.desc(), PlatformAccount.display_name.asc())
        if platform is not None:
            stmt = stmt.where(PlatformAccount.platform == platform)
        return stmt

    def _recent_attempts(self) -> list[PublishAttempt]:
        since = datetime.now(UTC) - timedelta(days=7)
        return list(self.db.scalars(select(PublishAttempt).where(PublishAttempt.created_at >= since).order_by(PublishAttempt.created_at.desc())))

    def _active_drafts(self) -> list[PublishDraft]:
        return list(
            self.db.scalars(
                select(PublishDraft).where(
                    PublishDraft.status.in_([PublishDraftStatus.READY, PublishDraftStatus.SCHEDULED, PublishDraftStatus.PUBLISHING])
                )
            )
        )

    def _build_stats(self, account: PlatformAccount, attempts: list[PublishAttempt], drafts: list[PublishDraft]) -> AccountHealthStats:
        succeeded = len([item for item in attempts if item.external_status == ExternalPublicationStatus.PUBLISHED])
        failed_items = [item for item in attempts if item.status == PublishAttemptStatus.FAILED]
        needs_reconciliation = len([item for item in attempts if item.status == PublishAttemptStatus.NEEDS_RECONCILIATION or item.reconciliation_required])
        success_rate = percent(succeeded, len(attempts))
        health_status, reasons = classify_account_health(
            account_status=account.status,
            is_on_hold=account.is_on_hold,
            cooldown_until=account.cooldown_until,
            attempts_7d=len(attempts),
            success_rate_percent=success_rate,
            failed_7d=len(failed_items),
            needs_reconciliation_count=needs_reconciliation,
        )
        return AccountHealthStats(
            platform_account_id=account.id,
            display_name=account.display_name,
            platform=account.platform,
            account_status=account.status,
            health_status=health_status,
            priority=account.priority,
            is_on_hold=account.is_on_hold,
            cooldown_until=account.cooldown_until,
            attempts_7d=len(attempts),
            succeeded_7d=succeeded,
            failed_7d=len(failed_items),
            needs_reconciliation_count=needs_reconciliation,
            assigned_draft_count=len(drafts),
            scheduled_draft_count=len([item for item in drafts if item.status == PublishDraftStatus.SCHEDULED]),
            recent_error_code=failed_items[0].error_code if failed_items else None,
            success_rate_percent=success_rate,
            reasons=reasons,
        )

