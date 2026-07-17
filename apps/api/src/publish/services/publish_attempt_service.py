from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishReconciliationStatus
from src.models.media import RenderOutput
from src.models.publish import PlatformAccount, PublishAttempt, PublishDraft
from src.publish.connectors.base import PublishConnector, PublishConnectorError
from src.publish.connectors.facebook_reels import FacebookReelsConnector
from src.publish.services.platform_account_service import PlatformAccountService
from src.publish.services.publish_gate_service import PublishGateService
from src.publish.services.publish_lifecycle_service import PublishLifecycleService
from src.publish.types import PublishMediaInput, PublishRequest
from src.schemas.publish import PublishDraftPublishRequest
from src.storage.local import LocalStorageBackend

logger = logging.getLogger(__name__)

ACTIVE_ATTEMPT_STATUSES = {
    PublishAttemptStatus.QUEUED,
    PublishAttemptStatus.RUNNING,
    PublishAttemptStatus.UPLOADING,
    PublishAttemptStatus.PUBLISHING,
    PublishAttemptStatus.AWAITING_PLATFORM_CONFIRMATION,
    PublishAttemptStatus.RECONCILING,
}


class PublishAttemptError(ValueError):
    pass


class PublishAttemptService:
    def __init__(self, db: Session, connector: PublishConnector | None = None):
        self.db = db
        self.connector = connector or FacebookReelsConnector()
        self.storage = LocalStorageBackend(get_settings().local_storage_root)
        self.lifecycle = PublishLifecycleService(db)

    def publish_now(self, draft_id: UUID, request: PublishDraftPublishRequest) -> PublishAttempt:
        draft = self._get_draft(draft_id)
        render = self._resolve_render(draft)
        account = self.db.get(PlatformAccount, request.platform_account_id)
        gate = PublishGateService(self.db).evaluate(draft, render, account)
        if not gate.allowed:
            raise PublishAttemptError("gate_blocked: " + "; ".join(gate.reasons))
        if account is None:
            raise PublishAttemptError("invalid_platform_account")
        self._assert_no_active_attempt(draft.id)

        attempt = self._create_attempt(draft, account, request)
        media_input = self._build_media_input(draft, render)
        attempt.request_summary_json = {
            "draft_id": str(draft.id),
            "render_output_id": str(render.id),
            "platform_account_id": str(account.id),
            "platform": draft.target_platform,
            "video_path": str(media_input.video_path),
            "mode": request.publish_mode,
        }
        attempt.warning_summary_json = {"warnings": gate.warnings}
        attempt.status = PublishAttemptStatus.RUNNING
        attempt.started_at = datetime.now(UTC)
        self._sync_draft(draft)
        self.db.commit()

        try:
            account_config = PlatformAccountService(self.db).resolve_config(account.id)
            attempt.status = PublishAttemptStatus.UPLOADING
            self._sync_draft(draft)
            self.db.commit()
            result = self.connector.publish(
                PublishRequest(
                    account=account_config,
                    media=media_input,
                    request_metadata={"publish_attempt_id": str(attempt.id)},
                )
            )
            attempt.status = result.status
            attempt.external_publish_id = result.external_publish_id
            attempt.external_media_id = result.external_media_id
            attempt.external_reel_id = result.external_reel_id
            attempt.external_permalink = result.external_permalink
            attempt.external_status = result.external_status
            attempt.reconciliation_required = result.reconciliation_required
            attempt.reconciliation_status = result.reconciliation_status
            attempt.response_summary_json = result.response_summary
            attempt.warning_summary_json = {"warnings": [*gate.warnings, *result.warnings]}
            if result.status == PublishAttemptStatus.SUCCEEDED and result.external_status == ExternalPublicationStatus.PUBLISHED:
                self.lifecycle.apply_success(attempt)
            else:
                attempt.status = result.status
                attempt.finished_at = datetime.now(UTC)
            self._sync_draft(draft)
            logger.info("publish_attempt_succeeded", extra={"publish_attempt_id": str(attempt.id), "draft_id": str(draft.id)})
        except PublishConnectorError as exc:
            attempt.response_summary_json = exc.response_summary
            self._apply_external_identifiers_from_response(attempt, exc.response_summary)
            self.lifecycle.apply_uncertain_failure(attempt, error_code=exc.code, error_message=str(exc))
            self._sync_draft(draft)
            logger.info("publish_attempt_failed", extra={"publish_attempt_id": str(attempt.id), "error_code": exc.code})
        except ValueError as exc:
            self.lifecycle.apply_uncertain_failure(attempt, error_code="invalid_platform_account", error_message=str(exc))
            self._sync_draft(draft)
            logger.info("publish_attempt_failed", extra={"publish_attempt_id": str(attempt.id), "error_code": "invalid_platform_account"})
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

    def refresh_attempt_status(self, attempt_id: UUID) -> PublishAttempt:
        attempt = self.get_attempt(attempt_id)
        if not (attempt.external_publish_id or attempt.external_media_id or attempt.external_reel_id):
            raise PublishAttemptError("missing_external_publish_reference")

        account_config = PlatformAccountService(self.db).resolve_config(attempt.platform_account_id)
        attempt.status = PublishAttemptStatus.RECONCILING
        attempt.reconciliation_status = PublishReconciliationStatus.IN_PROGRESS
        attempt.reconciliation_required = True
        self.db.commit()

        try:
            result = self.connector.refresh_status(
                account=account_config,
                external_publish_id=attempt.external_publish_id,
                external_media_id=attempt.external_media_id,
                external_reel_id=attempt.external_reel_id,
            )
            attempt.external_status = result.external_status
            attempt.external_permalink = result.external_permalink or attempt.external_permalink
            attempt.last_status_sync_result_json = {
                "external_status": result.external_status.value,
                "external_publish_id": result.external_publish_id,
                "external_permalink": result.external_permalink,
                "response_summary": result.response_summary,
                "warnings": result.warnings,
                "reconciliation_note": result.reconciliation_note,
            }
            attempt.warning_summary_json = {"warnings": [*(attempt.warning_summary_json or {}).get("warnings", []), *result.warnings]}
            self.lifecycle.mark_reconciled(attempt, result.external_status)
        except PublishConnectorError as exc:
            attempt.status = PublishAttemptStatus.NEEDS_RECONCILIATION
            attempt.reconciliation_status = PublishReconciliationStatus.UNRESOLVED
            attempt.reconciliation_required = True
            attempt.error_code = exc.code
            attempt.error_message = str(exc)
            attempt.last_status_checked_at = datetime.now(UTC)
            attempt.last_status_sync_result_json = {"error_code": exc.code, "error_message": str(exc), "response_summary": exc.response_summary}
            logger.info("publish_attempt_status_refresh_failed", extra={"publish_attempt_id": str(attempt.id), "error_code": exc.code})
        draft = self._get_draft(attempt.publish_draft_id)
        self._sync_draft(draft)
        self.db.commit()
        self.db.refresh(attempt)
        return attempt

    def list_attempts(
        self,
        *,
        publish_draft_id: UUID | None = None,
        status: PublishAttemptStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PublishAttempt]:
        stmt = select(PublishAttempt).order_by(PublishAttempt.created_at.desc()).limit(limit).offset(offset)
        if publish_draft_id is not None:
            stmt = stmt.where(PublishAttempt.publish_draft_id == publish_draft_id)
        if status is not None:
            stmt = stmt.where(PublishAttempt.status == status)
        return list(self.db.scalars(stmt))

    def get_attempt(self, attempt_id: UUID) -> PublishAttempt:
        attempt = self.db.get(PublishAttempt, attempt_id)
        if attempt is None:
            raise PublishAttemptError("Publish attempt not found")
        return attempt

    def latest_for_draft(self, draft_id: UUID) -> PublishAttempt | None:
        return self.db.scalar(
            select(PublishAttempt)
            .where(PublishAttempt.publish_draft_id == draft_id)
            .order_by(PublishAttempt.created_at.desc(), PublishAttempt.attempt_number.desc())
            .limit(1)
        )

    def canonical_for_draft(self, draft_id: UUID) -> PublishAttempt | None:
        draft = self._get_draft(draft_id)
        return self.db.get(PublishAttempt, draft.canonical_publish_attempt_id) if draft.canonical_publish_attempt_id else None

    def get_draft_for_status(self, draft_id: UUID) -> PublishDraft:
        return self._get_draft(draft_id)

    def attempts_for_draft(self, draft_id: UUID) -> list[PublishAttempt]:
        return list(
            self.db.scalars(
                select(PublishAttempt)
                .where(PublishAttempt.publish_draft_id == draft_id)
                .order_by(PublishAttempt.created_at.desc(), PublishAttempt.attempt_number.desc())
            )
        )

    def _get_draft(self, draft_id: UUID) -> PublishDraft:
        draft = self.db.get(PublishDraft, draft_id)
        if draft is None:
            raise PublishAttemptError("Publish draft not found")
        return draft

    def _resolve_render(self, draft: PublishDraft) -> RenderOutput:
        render = self.db.get(RenderOutput, draft.render_output_id) if draft.render_output_id else None
        if render is None:
            raise PublishAttemptError("missing_render_output")
        return render

    def _assert_no_active_attempt(self, draft_id: UUID) -> None:
        active = self.db.scalar(
            select(PublishAttempt)
            .where(PublishAttempt.publish_draft_id == draft_id, PublishAttempt.status.in_(ACTIVE_ATTEMPT_STATUSES))
            .limit(1)
        )
        if active is not None:
            raise PublishAttemptError("duplicate_active_attempt")

    def _create_attempt(
        self,
        draft: PublishDraft,
        account: PlatformAccount,
        request: PublishDraftPublishRequest,
    ) -> PublishAttempt:
        attempt_number = int(
            self.db.scalar(select(func.coalesce(func.max(PublishAttempt.attempt_number), 0)).where(PublishAttempt.publish_draft_id == draft.id))
            or 0
        ) + 1
        attempt = PublishAttempt(
            workspace_id=draft.workspace_id,
            publish_draft_id=draft.id,
            platform=account.platform,
            platform_account_id=account.id,
            attempt_number=attempt_number,
            status=PublishAttemptStatus.QUEUED,
            metadata_json={"publish_mode": request.publish_mode},
        )
        self.db.add(attempt)
        self.db.flush()
        return attempt

    def _sync_draft(self, draft: PublishDraft) -> None:
        self.lifecycle.sync_attempt_to_draft(draft, self.attempts_for_draft(draft.id))

    def _apply_external_identifiers_from_response(self, attempt: PublishAttempt, response_summary: dict | None) -> None:
        if not response_summary:
            return
        for key in ("external_publish_id", "publish_id", "post_id", "id"):
            value = response_summary.get(key)
            if isinstance(value, str) and value:
                attempt.external_publish_id = attempt.external_publish_id or value
                break
        for key in ("external_media_id", "video_id", "media_id"):
            value = response_summary.get(key)
            if isinstance(value, str) and value:
                attempt.external_media_id = attempt.external_media_id or value
                break
        for key in ("external_reel_id", "reel_id"):
            value = response_summary.get(key)
            if isinstance(value, str) and value:
                attempt.external_reel_id = attempt.external_reel_id or value
                break

    def _build_media_input(self, draft: PublishDraft, render: RenderOutput) -> PublishMediaInput:
        if render.media_asset is None:
            raise PublishAttemptError("missing_render_output")
        video_path = self.storage.resolve(render.media_asset.storage_key).absolute_path
        hashtags = " ".join(f"#{item.get('tag')}" for item in (draft.hashtags_json or []) if isinstance(item, dict) and item.get("tag"))
        description = "\n".join(part for part in [draft.caption, draft.cta_text, hashtags] if part)
        return PublishMediaInput(
            publish_draft_id=draft.id,
            render_output_id=render.id,
            source_video_id=draft.source_video_id,
            video_path=video_path,
            title=draft.title or "Reup Douyin video",
            description=description,
        )
