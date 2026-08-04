from __future__ import annotations

import logging
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.enums import (
    ExternalPublicationStatus,
    PlatformAccountStatus,
    PublishAttemptStatus,
    PublishDraftStatus,
    PublishReconciliationStatus,
    PublishTargetPlatform,
)
from src.models.media import RenderOutput
from src.models.publish import PlatformAccount, PlatformPublication, PublishAttempt, PublishDraft
from src.publish.services.publish_lifecycle_service import PublishLifecycleService
from src.schemas.publish import ExistingFacebookReelRegisterRequest, FacebookReelDiscoveryImportRequest


class PlatformPublicationError(ValueError):
    pass


logger = logging.getLogger(__name__)


class PlatformPublicationService:
    """Materialize externally confirmed posts without conflating them with attempts."""

    def __init__(self, db: Session):
        self.db = db
        self.lifecycle = PublishLifecycleService(db)

    def sync_for_draft(self, draft_id: UUID) -> PlatformPublication | None:
        draft = self.db.get(PublishDraft, draft_id)
        if draft is None:
            raise PlatformPublicationError("Publish draft not found")

        attempts = list(
            self.db.scalars(
                select(PublishAttempt)
                .where(PublishAttempt.publish_draft_id == draft.id)
                .order_by(PublishAttempt.attempt_number.asc())
            )
        )
        publications = list(
            self.db.scalars(
                select(PlatformPublication).where(PlatformPublication.publish_draft_id == draft.id)
            )
        )
        by_attempt_id = {row.publish_attempt_id: row for row in publications}
        canonical_publication: PlatformPublication | None = None
        fingerprint = self._render_fingerprint(draft.render_output_id)

        for publication in publications:
            publication.is_canonical = False

        for attempt in attempts:
            external_id = self._external_identity(attempt)
            publication = by_attempt_id.get(attempt.id)
            if publication is None and external_id:
                publication = self.db.scalar(
                    select(PlatformPublication).where(
                        PlatformPublication.workspace_id == draft.workspace_id,
                        PlatformPublication.platform == attempt.platform,
                        PlatformPublication.platform_account_id == attempt.platform_account_id,
                        PlatformPublication.external_publish_id == external_id,
                    )
                )

            confirmed_published = attempt.external_status == ExternalPublicationStatus.PUBLISHED
            if publication is None and (not external_id or not confirmed_published):
                continue
            if publication is None:
                publication = PlatformPublication(
                    workspace_id=draft.workspace_id,
                    publish_draft_id=draft.id,
                    source_video_id=draft.source_video_id,
                    render_output_id=draft.render_output_id,
                    platform=attempt.platform,
                    platform_account_id=attempt.platform_account_id,
                    publish_attempt_id=attempt.id,
                    external_publish_id=external_id,
                    origin=self._attempt_origin(attempt),
                    native_product_placement_status="NOT_EVALUATED",
                    affiliate_comment_status="NOT_PLANNED",
                )
                self.db.add(publication)
                by_attempt_id[attempt.id] = publication
            elif attempt.id == draft.canonical_publish_attempt_id:
                publication.publish_attempt_id = attempt.id

            publication.external_media_id = attempt.external_media_id
            publication.external_reel_id = attempt.external_reel_id
            publication.external_permalink = attempt.external_permalink
            publication.status = attempt.external_status
            publication.last_synced_at = (
                attempt.last_status_checked_at or attempt.finished_at or datetime.now(UTC)
            )
            if confirmed_published and publication.published_at is None:
                publication.published_at = attempt.finished_at or attempt.last_status_checked_at or datetime.now(UTC)
            publication.content_fingerprint_sha256 = fingerprint
            publication.origin = self._attempt_origin(attempt)
            publication.is_canonical = attempt.id == draft.canonical_publish_attempt_id
            publication.metadata_json = {
                **(publication.metadata_json or {}),
                "authority_version": "PLATFORM_PUBLICATION_V1",
                "source_attempt_number": attempt.attempt_number,
            }
            if publication.is_canonical:
                canonical_publication = publication

        self.db.flush()
        return canonical_publication

    def register_existing_facebook_reel(
        self,
        request: ExistingFacebookReelRegisterRequest,
    ) -> PlatformPublication:
        """Register operator-verified external evidence without calling Facebook."""

        draft = self.db.get(PublishDraft, request.publish_draft_id)
        if draft is None:
            raise PlatformPublicationError("Publish draft not found")
        account = self.db.get(PlatformAccount, request.platform_account_id)
        if account is None:
            raise PlatformPublicationError("Platform account not found")
        if account.workspace_id != draft.workspace_id:
            raise PlatformPublicationError("Platform account and publish draft must share a workspace")
        if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
            raise PlatformPublicationError("Existing Reel registration requires a FACEBOOK_REELS account")
        if draft.target_platform != PublishTargetPlatform.FACEBOOK_REELS.value:
            raise PlatformPublicationError("Publish draft must target FACEBOOK_REELS")
        if account.status != PlatformAccountStatus.ACTIVE or account.is_on_hold:
            raise PlatformPublicationError("Facebook Page account must be ACTIVE and not on hold")
        if account.cooldown_until and account.cooldown_until > datetime.now(UTC):
            raise PlatformPublicationError("Facebook Page account is in cooldown")

        existing = self.db.scalar(
            select(PlatformPublication).where(
                PlatformPublication.workspace_id == draft.workspace_id,
                PlatformPublication.platform == PublishTargetPlatform.FACEBOOK_REELS,
                PlatformPublication.platform_account_id == account.id,
                PlatformPublication.external_publish_id == request.external_publish_id,
            )
        )
        if existing is not None:
            if existing.publish_draft_id != draft.id:
                raise PlatformPublicationError("Facebook Reel is already registered to another publish draft")
            return existing

        attempt_number = int(
            self.db.scalar(
                select(func.coalesce(func.max(PublishAttempt.attempt_number), 0)).where(
                    PublishAttempt.publish_draft_id == draft.id
                )
            )
            or 0
        ) + 1
        now = datetime.now(UTC)
        media_id = request.external_reel_id or request.external_media_id or request.external_publish_id
        attempt = PublishAttempt(
            workspace_id=draft.workspace_id,
            publish_draft_id=draft.id,
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            platform_account_id=account.id,
            attempt_number=attempt_number,
            status=PublishAttemptStatus.RECONCILED,
            started_at=now,
            finished_at=request.published_at,
            external_publish_id=request.external_publish_id,
            external_media_id=request.external_media_id or media_id,
            external_reel_id=request.external_reel_id or media_id,
            external_permalink=request.external_permalink,
            external_status=ExternalPublicationStatus.PUBLISHED,
            reconciliation_status=PublishReconciliationStatus.RESOLVED_SUCCESS,
            reconciliation_required=False,
            last_status_checked_at=now,
            request_summary_json={
                "mode": "manual_import",
                "draft_id": str(draft.id),
                "platform_account_id": str(account.id),
                "operator_attestation": request.operator_attestation,
            },
            response_summary_json={
                "source": "operator_verified_existing_facebook_reel",
                "external_network_called": False,
            },
            warning_summary_json={"warnings": ["manual_publication_import"]},
            metadata_json={
                "publication_origin": "MANUAL_IMPORT",
                "external_network_called": False,
                "registered_at": now.isoformat(),
            },
        )
        self.db.add(attempt)
        try:
            self.db.flush()
            attempts = list(
                self.db.scalars(
                    select(PublishAttempt)
                    .where(PublishAttempt.publish_draft_id == draft.id)
                    .order_by(PublishAttempt.created_at.desc(), PublishAttempt.attempt_number.desc())
                )
            )
            self.lifecycle.sync_attempt_to_draft(draft, attempts)
            publication = self.sync_for_draft(draft.id)
            if publication is None:
                raise PlatformPublicationError("Manual publication authority could not be materialized")
            publication.origin = "MANUAL_IMPORT"
            publication.published_at = request.published_at
            publication.last_synced_at = now
            publication.metadata_json = {
                **(publication.metadata_json or {}),
                "authority_origin": "MANUAL_IMPORT",
                "operator_attestation": request.operator_attestation,
                "facebook_insights_verified_media_id": media_id,
                "facebook_insights_object_verified_at": now.isoformat(),
                "external_network_called": False,
            }
            draft.status = PublishDraftStatus.PUBLISHED
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PlatformPublicationError("Facebook Reel is already registered") from exc
        self.db.refresh(publication)
        return publication

    def import_discovered_facebook_reel(
        self,
        request: FacebookReelDiscoveryImportRequest,
        *,
        workspace_id: UUID,
    ) -> PlatformPublication:
        """Persist one read-only Graph discovery fact without inventing a publish attempt."""

        account = self.db.get(PlatformAccount, request.platform_account_id)
        if account is None or account.workspace_id != workspace_id:
            raise PlatformPublicationError("Facebook Page account not found")
        if account.platform != PublishTargetPlatform.FACEBOOK_REELS:
            raise PlatformPublicationError("Discovered Reel requires a FACEBOOK_REELS account")
        existing = self.db.scalar(
            select(PlatformPublication).where(
                PlatformPublication.workspace_id == workspace_id,
                PlatformPublication.platform == PublishTargetPlatform.FACEBOOK_REELS,
                PlatformPublication.platform_account_id == account.id,
                PlatformPublication.external_publish_id == request.reel_id,
            )
        )
        now = datetime.now(UTC)
        if existing is None:
            publication = PlatformPublication(
                workspace_id=workspace_id,
                publish_draft_id=None,
                source_video_id=None,
                render_output_id=None,
                platform=PublishTargetPlatform.FACEBOOK_REELS,
                platform_account_id=account.id,
                publish_attempt_id=None,
                external_publish_id=request.reel_id,
                external_media_id=request.reel_id,
                external_reel_id=request.reel_id,
                external_permalink=request.permalink_url,
                status=ExternalPublicationStatus.PUBLISHED,
                is_canonical=False,
                published_at=request.created_time,
                last_synced_at=now,
                origin="FACEBOOK_DISCOVERY",
                native_product_placement_status="NOT_EVALUATED",
                affiliate_comment_status="NOT_PLANNED",
            )
            self.db.add(publication)
        else:
            publication = existing
            publication.external_permalink = request.permalink_url or publication.external_permalink
            publication.published_at = request.created_time or publication.published_at
            publication.last_synced_at = now
            publication.status = ExternalPublicationStatus.PUBLISHED
        publication.metadata_json = {
            **(publication.metadata_json or {}),
            "authority_version": "PLATFORM_PUBLICATION_V2",
            "authority_origin": "FACEBOOK_DISCOVERY",
            "facebook_insights_verified_media_id": request.reel_id,
            "facebook_insights_object_verified_at": now.isoformat(),
            "external_caption": request.description,
            "thumbnail_url": request.thumbnail_url,
            "discovered_at": now.isoformat(),
            "external_network_called": True,
        }
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            # A second operator click can race the first transaction. Re-read the
            # canonical row after rollback and return it instead of reporting a
            # failure for a publication that was actually persisted.
            publication = self.db.scalar(
                select(PlatformPublication).where(
                    PlatformPublication.workspace_id == workspace_id,
                    PlatformPublication.platform == PublishTargetPlatform.FACEBOOK_REELS,
                    PlatformPublication.platform_account_id == account.id,
                    PlatformPublication.external_publish_id == request.reel_id,
                )
            )
            if publication is None:
                raise PlatformPublicationError("Facebook Reel is already imported") from exc
            logger.info(
                "facebook_reel_import_race_recovered workspace_id=%s platform_account_id=%s publication_id=%s",
                workspace_id,
                account.id,
                publication.id,
            )
        self.db.refresh(publication)
        logger.info(
            "facebook_reel_imported workspace_id=%s platform_account_id=%s publication_id=%s origin=%s",
            workspace_id,
            account.id,
            publication.id,
            publication.origin,
        )
        if request.publish_draft_id is not None:
            return self.link_draft(
                publication.id,
                request.publish_draft_id,
                workspace_id=workspace_id,
            )
        return publication

    def link_draft(
        self,
        publication_id: UUID,
        publish_draft_id: UUID,
        *,
        workspace_id: UUID,
    ) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None or publication.workspace_id != workspace_id:
            raise PlatformPublicationError("Platform publication not found")
        draft = self.db.get(PublishDraft, publish_draft_id)
        if draft is None or draft.workspace_id != workspace_id:
            raise PlatformPublicationError("Publish draft not found")
        if draft.target_platform != publication.platform.value:
            raise PlatformPublicationError("Publish draft platform does not match publication")
        if publication.publish_draft_id not in {None, draft.id}:
            raise PlatformPublicationError("Publication is already linked to another publish draft")
        if (
            draft.current_external_publish_id
            and draft.current_external_publish_id != publication.external_publish_id
        ):
            raise PlatformPublicationError("Publish draft is already linked to another external publication")
        self.db.execute(
            PlatformPublication.__table__.update()
            .where(
                PlatformPublication.publish_draft_id == draft.id,
                PlatformPublication.id != publication.id,
            )
            .values(is_canonical=False)
        )
        now = datetime.now(UTC)
        publication.publish_draft_id = draft.id
        publication.source_video_id = draft.source_video_id
        publication.render_output_id = draft.render_output_id
        publication.is_canonical = True
        publication.metadata_json = {
            **(publication.metadata_json or {}),
            "linked_to_publish_draft_at": now.isoformat(),
        }
        draft.status = PublishDraftStatus.PUBLISHED
        draft.current_publication_status = publication.status
        draft.current_external_publish_id = publication.external_publish_id
        draft.current_external_permalink = publication.external_permalink
        draft.published_at = publication.published_at
        draft.last_publish_synced_at = publication.last_synced_at or now
        draft.publication_summary_json = {
            **(draft.publication_summary_json or {}),
            "origin": publication.origin,
            "platform_publication_id": str(publication.id),
            "linked_without_publish_attempt": publication.publish_attempt_id is None,
        }
        self.db.commit()
        self.db.refresh(publication)
        return publication

    def list_publications(
        self,
        *,
        platform: PublishTargetPlatform | None = None,
        platform_account_id: UUID | None = None,
        status: ExternalPublicationStatus | None = None,
        publish_draft_id: UUID | None = None,
        workspace_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[PlatformPublication], int]:
        filters = []
        if workspace_id is not None:
            filters.append(PlatformPublication.workspace_id == workspace_id)
        if platform is not None:
            filters.append(PlatformPublication.platform == platform)
        if platform_account_id is not None:
            filters.append(PlatformPublication.platform_account_id == platform_account_id)
        if status is not None:
            filters.append(PlatformPublication.status == status)
        if publish_draft_id is not None:
            filters.append(PlatformPublication.publish_draft_id == publish_draft_id)

        stmt = select(PlatformPublication).where(*filters).order_by(
            PlatformPublication.published_at.desc().nullslast(),
            PlatformPublication.created_at.desc(),
        )
        total = int(
            self.db.scalar(select(func.count()).select_from(PlatformPublication).where(*filters)) or 0
        )
        rows = list(self.db.scalars(stmt.limit(limit).offset(offset)))
        return rows, total

    def get_publication(self, publication_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None:
            raise PlatformPublicationError("Platform publication not found")
        return publication

    def canonical_for_draft(self, draft_id: UUID) -> PlatformPublication | None:
        return self.db.scalar(
            select(PlatformPublication)
            .where(
                PlatformPublication.publish_draft_id == draft_id,
                PlatformPublication.is_canonical.is_(True),
            )
            .limit(1)
        )

    def _render_fingerprint(self, render_output_id: UUID | None) -> str | None:
        if render_output_id is None:
            return None
        render = self.db.get(RenderOutput, render_output_id)
        asset = render.media_asset if render is not None else None
        checksum = getattr(asset, "checksum_sha256", None)
        return str(checksum) if checksum else None

    @staticmethod
    def _external_identity(attempt: PublishAttempt) -> str | None:
        return attempt.external_publish_id or attempt.external_reel_id or attempt.external_media_id

    @staticmethod
    def _attempt_origin(attempt: PublishAttempt) -> str:
        metadata = getattr(attempt, "metadata_json", None) or {}
        return "MANUAL_IMPORT" if metadata.get("publication_origin") == "MANUAL_IMPORT" else "CONNECTOR_PUBLISH"
