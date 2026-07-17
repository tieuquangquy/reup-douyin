from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from src.enums import PublishAccountAssignmentStatus
from src.models.publish import PlatformAccount, PublishDraft
from src.publish_routing.services.account_eligibility_service import AccountEligibilityService
from src.publish_routing.services.account_health_service import AccountHealthService
from src.publish_routing.types import AccountEligibility
from src.schemas.publish_routing import BulkAssignDraftsRequest, DraftAssignmentRequest


class DraftAssignmentError(ValueError):
    pass


class DraftAssignmentService:
    def __init__(self, db: Session):
        self.db = db
        self.health_service = AccountHealthService(db)
        self.eligibility_service = AccountEligibilityService()

    def assign(self, draft_id: UUID, request: DraftAssignmentRequest) -> PublishDraft:
        draft = self._draft(draft_id)
        account = self._account(request.platform_account_id)
        eligibility = self._validate_assignment(draft, account, request)
        self._apply_assignment(draft, account, eligibility, request)
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def unassign(self, draft_id: UUID) -> PublishDraft:
        draft = self._draft(draft_id)
        draft.assigned_platform_account_id = None
        draft.platform_account_ref = None
        draft.assignment_status = PublishAccountAssignmentStatus.UNASSIGNED
        draft.assigned_at = None
        draft.assigned_reason = None
        draft.assigned_by = None
        draft.assignment_metadata_json = None
        self.db.commit()
        self.db.refresh(draft)
        return draft

    def bulk_assign(self, request: BulkAssignDraftsRequest) -> list[PublishDraft]:
        account = self._account(request.platform_account_id)
        drafts = [self._draft(draft_id) for draft_id in request.publish_draft_ids]
        validations = [(draft, self._validate_assignment(draft, account, request)) for draft in drafts]
        # Mutate only after every draft has passed validation, so bulk assignment is all-or-nothing.
        for draft, eligibility in validations:
            self._apply_assignment(draft, account, eligibility, request)
        self.db.commit()
        for draft in drafts:
            self.db.refresh(draft)
        return drafts

    def _validate_assignment(self, draft: PublishDraft, account: PlatformAccount, request: DraftAssignmentRequest | BulkAssignDraftsRequest) -> AccountEligibility:
        if account.workspace_id != draft.workspace_id:
            raise DraftAssignmentError("Platform account does not belong to the draft workspace")
        health = self.health_service.account_health(account)
        eligibility = self.eligibility_service.evaluate(draft=draft, account=account, health=health)
        if not eligibility.eligible and not request.force_override:
            raise DraftAssignmentError("; ".join(eligibility.blocking_reasons) or "Account is not eligible for this draft")
        return eligibility

    def _apply_assignment(
        self,
        draft: PublishDraft,
        account: PlatformAccount,
        eligibility: AccountEligibility,
        request: DraftAssignmentRequest | BulkAssignDraftsRequest,
    ) -> None:
        draft.assigned_platform_account_id = account.id
        draft.platform_account_ref = account.external_account_id
        draft.assignment_status = PublishAccountAssignmentStatus.OVERRIDDEN if not eligibility.eligible else PublishAccountAssignmentStatus.ASSIGNED
        draft.assigned_at = datetime.now(UTC)
        draft.assigned_reason = request.reason or ("manual override" if not eligibility.eligible else "manual assignment")
        draft.assigned_by = request.assigned_by
        draft.assignment_metadata_json = {
            "force_override": request.force_override,
            "eligibility_score": eligibility.score,
            "blocking_reasons": eligibility.blocking_reasons,
            "warnings": eligibility.warnings,
        }

    def _draft(self, draft_id: UUID) -> PublishDraft:
        draft = self.db.get(PublishDraft, draft_id)
        if draft is None:
            raise DraftAssignmentError("Publish draft not found")
        return draft

    def _account(self, account_id: UUID) -> PlatformAccount:
        account = self.db.get(PlatformAccount, account_id)
        if account is None:
            raise DraftAssignmentError("Platform account not found")
        return account
