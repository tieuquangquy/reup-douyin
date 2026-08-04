from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from ipaddress import ip_address
import logging
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from src.enums import JobStatus, JobType, PlatformAccountStatus, PublishTargetPlatform
from src.growth_intelligence.services.growth_score_service import GrowthScoreService, STALE_MEASUREMENT_SECONDS
from src.models.affiliate import AffiliateCommentPlacement, AffiliateProduct, AffiliateProductMatch
from src.models.analytics import PublicationGrowthAssessment, PublicationMetricSnapshot
from src.models.jobs import Job
from src.models.publish import PlatformAccount, PlatformPublication
from src.publish.connectors.base import PublishConnectorError
from src.publish.connectors.facebook_reels import FacebookReelsConnector
from src.publish.services.platform_account_service import PlatformAccountError, PlatformAccountService
from src.publish.services.facebook_publish_safety_service import FacebookPublishSafetyService
from src.schemas.affiliate_comment import AffiliateCommentPreviewRequest
from src.affiliate_intelligence.services.affiliate_comment_template_service import (
    AffiliateCommentTemplateError,
    AffiliateCommentTemplateService,
)
from src.schemas.affiliate_comment_template import DEFAULT_CTA, DEFAULT_DISCLOSURE
from src.services.job_service import JobService


logger = logging.getLogger(__name__)

AFFILIATE_COMMENT_COOLDOWN_HOURS = 6
AFFILIATE_COMMENT_MAX_POSTS_PER_24H = 2


class AffiliateCommentError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class AffiliateCommentService:
    def __init__(self, db: Session):
        self.db = db
        self.growth = GrowthScoreService(db)
        self.accounts = PlatformAccountService(db)
        self.templates = AffiliateCommentTemplateService(db)

    def preview(
        self,
        publication_id: UUID,
        workspace_id: UUID,
        operator_subject: str,
        request: AffiliateCommentPreviewRequest,
    ) -> tuple[AffiliateCommentPlacement, bool]:
        context = self._load_context(publication_id, workspace_id)
        self._validate_gates(context)
        product = context["product"]
        template = self.templates.get(workspace_id, request.template_id) if request.template_id else self.templates.active(workspace_id)
        if template is not None and template.platform != "FACEBOOK_REELS":
            raise AffiliateCommentError("affiliate_comment_template_platform_invalid", "The active template does not support Facebook Reels")
        cta = (
            request.cta_text.strip()
            if request.replaces_placement_id or template is None
            else template.default_cta.strip()
        )
        disclosure = (
            request.disclosure_text.strip()
            if request.replaces_placement_id or template is None
            else template.default_disclosure.strip()
        )
        attach_product_image = (
            request.attach_product_image
            if request.attach_product_image is not None
            else template.attach_product_image if template is not None else True
        )
        attachment_image_url = self._comment_image_url(product.image_url) if attach_product_image else None
        render_variables = {
            "cta": cta,
            "product_name": product.name,
            "description": getattr(product, "description", None) or "",
            "affiliate_url": product.affiliate_url,
            "disclosure": disclosure,
            "page_name": getattr(context.get("account"), "display_name", "") or "",
            "reel_title": getattr(context.get("publication"), "caption", None) or "",
            "topic_name": "",
            "product_image": "",
        }
        comment_source = request.comment_source
        custom_message_template = request.comment_message_template_override
        affiliate_url_auto_appended = False
        if comment_source == "ITEM_CUSTOM" and custom_message_template and re.search(r"{{\s*product_image\s*}}", custom_message_template, re.IGNORECASE):
            attach_product_image = True
            attachment_image_url = self._comment_image_url(product.image_url)
        comment_override = request.comment_message_override
        if comment_source == "ITEM_CUSTOM":
            if custom_message_template is None:
                raise AffiliateCommentError(
                    "affiliate_comment_custom_template_required",
                    "Custom item comment content is required",
                )
            try:
                self.templates.validate_custom_template(custom_message_template)
                message = self.templates.render(custom_message_template, render_variables)
            except AffiliateCommentTemplateError as exc:
                raise AffiliateCommentError(exc.code, str(exc)) from exc
            if product.affiliate_url not in message:
                message = f"{message.rstrip()}\n\n{product.affiliate_url}".strip()
                affiliate_url_auto_appended = True
            self._validate_comment_message(message, product.affiliate_url)
        elif comment_override is not None:
            if request.replaces_placement_id is None:
                raise AffiliateCommentError(
                    "affiliate_comment_override_requires_revision",
                    "A custom comment message can only replace an existing draft preview",
                )
            self._validate_comment_message(comment_override, product.affiliate_url)
            message = comment_override
        elif template is None:
            message = f"{cta}\n{product.name}\n{product.affiliate_url}\n\n{disclosure}"
        else:
            try:
                message = self.templates.render(template.message_template, render_variables)
            except AffiliateCommentTemplateError as exc:
                raise AffiliateCommentError(exc.code, str(exc)) from exc
        message_hash = hashlib.sha256(message.encode("utf-8")).hexdigest()
        attachment_hash = hashlib.sha256((attachment_image_url or "").encode("utf-8")).hexdigest()[:12]
        idempotency_key = (
            f"affiliate-comment:{publication_id}:{context['product_match'].id}:"
            f"{message_hash[:24]}:{attachment_hash}"
        )
        if request.replaces_placement_id:
            idempotency_key = f"{idempotency_key}:replace:{request.replaces_placement_id}"
        elif request.create_another_comment:
            idempotency_key = f"{idempotency_key}:another:{request.previous_posted_placement_id}"
        existing = self.db.scalar(
            select(AffiliateCommentPlacement).where(
                AffiliateCommentPlacement.workspace_id == workspace_id,
                AffiliateCommentPlacement.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.is_current:
                return existing, True
            raise AffiliateCommentError(
                "affiliate_comment_preview_changed",
                "This preview revision is no longer current; reload before editing",
            )
        current = self.db.scalar(
            select(AffiliateCommentPlacement).where(
                AffiliateCommentPlacement.workspace_id == workspace_id,
                AffiliateCommentPlacement.platform_publication_id == publication_id,
                AffiliateCommentPlacement.is_current.is_(True),
            ).with_for_update()
        )
        if request.replaces_placement_id:
            if current is None or current.id != request.replaces_placement_id:
                raise AffiliateCommentError(
                    "affiliate_comment_preview_changed",
                    "The affiliate comment preview changed; reload before saving your edit",
                )
            if current.status not in {"DRAFT", "FAILED"}:
                raise AffiliateCommentError(
                    "affiliate_comment_preview_locked",
                    f"A {current.status.lower()} affiliate comment preview cannot be edited",
                )
        elif request.create_another_comment:
            if (
                current is None
                or current.id != request.previous_posted_placement_id
                or current.status != "POSTED"
            ):
                raise AffiliateCommentError(
                    "affiliate_comment_previous_changed",
                    "The previously posted comment changed; reload before creating another comment",
                )
            posted_history, policy = self._another_comment_policy(publication_id, workspace_id, current=current)
            if not policy["can_create_another"]:
                raise AffiliateCommentError(
                    "affiliate_comment_daily_limit",
                    "This Reel already has two affiliate comments in the last 24 hours",
                )
            if any(item.message_sha256 == message_hash for item in posted_history):
                raise AffiliateCommentError(
                    "affiliate_comment_duplicate",
                    "The new affiliate comment must use different content from previously posted comments",
                )
        elif current is not None:
            if current.status in {"DRAFT", "FAILED"}:
                raise AffiliateCommentError(
                    "affiliate_comment_already_exists",
                    "This Reel already has an editable preview; use Edit preview to regenerate it",
                )
            raise AffiliateCommentError(
                "affiliate_comment_preview_locked",
                f"This Reel already has a {current.status.lower()} affiliate comment placement",
            )
        self.db.execute(
            update(AffiliateCommentPlacement)
            .where(
                AffiliateCommentPlacement.platform_publication_id == publication_id,
                AffiliateCommentPlacement.is_current.is_(True),
            )
            .values(is_current=False)
        )
        growth_assessment = context["assessment"]
        placement = AffiliateCommentPlacement(
            workspace_id=workspace_id,
            platform_publication_id=publication_id,
            platform_account_id=context["account"].id,
            affiliate_product_match_id=context["product_match"].id,
            selected_product_id=product.id,
            growth_assessment_id=growth_assessment.id,
            status="DRAFT",
            idempotency_key=idempotency_key,
            message_sha256=message_hash,
            comment_message=message,
            cta_text=cta,
            disclosure_text=disclosure,
            affiliate_url=product.affiliate_url,
            attachment_image_url=attachment_image_url,
            template_id=template.id if template and comment_source == "SHARED_TEMPLATE" else None,
            template_version=template.version if template and comment_source == "SHARED_TEMPLATE" else None,
            attach_product_image=attach_product_image,
            external_reel_id=self._external_reel_id(context["publication"]),
            created_by=operator_subject[:180],
            is_current=True,
            gate_snapshot_json=self._gate_snapshot(context),
            metadata_json={
                "automatic_placement": False,
                "preview_only": True,
                "revision_number": int((current.metadata_json or {}).get("revision_number") or 1) + 1
                if current and request.replaces_placement_id
                else 1,
                "replaces_placement_id": str(current.id) if current and request.replaces_placement_id else None,
                "placement_sequence": int((current.metadata_json or {}).get("placement_sequence") or 1) + 1
                if current and request.create_another_comment
                else int((current.metadata_json or {}).get("placement_sequence") or 1) if current else 1,
                "previous_posted_placement_id": str(request.previous_posted_placement_id)
                if request.create_another_comment
                else (current.metadata_json or {}).get("previous_posted_placement_id") if current else None,
                "comment_source": comment_source,
                "template_name": template.name if template and comment_source == "SHARED_TEMPLATE" else None,
                "template_version": template.version if template and comment_source == "SHARED_TEMPLATE" else None,
                "template_was_active_at_preview": bool(template.is_active) if template and comment_source == "SHARED_TEMPLATE" else comment_source == "ITEM_CUSTOM",
                "comment_message_template_override": custom_message_template if comment_source == "ITEM_CUSTOM" else None,
                "comment_message_overridden": comment_override is not None or comment_source == "ITEM_CUSTOM",
                "affiliate_url_auto_appended": affiliate_url_auto_appended if comment_source == "ITEM_CUSTOM" else False,
            },
        )
        self.db.add(placement)
        self.db.flush()
        if current is not None:
            if request.create_another_comment:
                current.metadata_json = {
                    **(current.metadata_json or {}),
                    "next_comment_created_at": datetime.now(UTC).isoformat(),
                    "next_comment_placement_id": str(placement.id),
                }
            else:
                current.metadata_json = {
                    **(current.metadata_json or {}),
                    "superseded_at": datetime.now(UTC).isoformat(),
                    "superseded_by_placement_id": str(placement.id),
                }
        context["publication"].affiliate_comment_status = "DRAFT"
        self.db.commit()
        self.db.refresh(placement)
        logger.info(
            "affiliate_comment_preview_created",
            extra={
                "workspace_id": str(workspace_id),
                "publication_id": str(publication_id),
                "placement_id": str(placement.id),
                "replaces_placement_id": str(current.id) if current and request.replaces_placement_id else None,
                "previous_posted_placement_id": str(request.previous_posted_placement_id)
                if request.create_another_comment
                else None,
            },
        )
        return placement, False

    def get_current(self, publication_id: UUID, workspace_id: UUID) -> AffiliateCommentPlacement | None:
        self._publication(publication_id, workspace_id)
        return self.db.scalar(
            select(AffiliateCommentPlacement).where(
                AffiliateCommentPlacement.workspace_id == workspace_id,
                AffiliateCommentPlacement.platform_publication_id == publication_id,
                AffiliateCommentPlacement.is_current.is_(True),
            )
        )

    def list_history(
        self,
        publication_id: UUID,
        workspace_id: UUID,
    ) -> tuple[list[AffiliateCommentPlacement], dict[str, object]]:
        self._publication(publication_id, workspace_id)
        placements = list(
            self.db.scalars(
                select(AffiliateCommentPlacement)
                .where(
                    AffiliateCommentPlacement.workspace_id == workspace_id,
                    AffiliateCommentPlacement.platform_publication_id == publication_id,
                )
                .order_by(AffiliateCommentPlacement.created_at.desc())
            )
        )
        current = next((placement for placement in placements if placement.is_current), None)
        policy_current = current
        previous_id = str((current.metadata_json or {}).get("previous_posted_placement_id") or "") if current else ""
        if current and current.status in {"DRAFT", "FAILED"} and previous_id:
            policy_current = next((placement for placement in placements if str(placement.id) == previous_id), current)
        _, policy = self._another_comment_policy(
            publication_id,
            workspace_id,
            current=policy_current,
            posted_history=[placement for placement in placements if placement.status == "POSTED"],
        )
        return placements, policy

    def _another_comment_policy(
        self,
        publication_id: UUID,
        workspace_id: UUID,
        *,
        current: AffiliateCommentPlacement | None,
        posted_history: list[AffiliateCommentPlacement] | None = None,
    ) -> tuple[list[AffiliateCommentPlacement], dict[str, object]]:
        if posted_history is None:
            posted_history = list(
                self.db.scalars(
                    select(AffiliateCommentPlacement)
                    .where(
                        AffiliateCommentPlacement.workspace_id == workspace_id,
                        AffiliateCommentPlacement.platform_publication_id == publication_id,
                        AffiliateCommentPlacement.status == "POSTED",
                    )
                    .order_by(AffiliateCommentPlacement.posted_at.desc())
                )
            )
        now = datetime.now(UTC)
        posted_history.sort(key=lambda item: self._utc_datetime(item.posted_at or item.created_at), reverse=True)
        recent = [
            placement
            for placement in posted_history
            if self._utc_datetime(placement.posted_at or placement.created_at) >= now - timedelta(hours=24)
        ]
        blocked_reason: str | None = None
        next_allowed_at: datetime | None = None
        if current is None or current.status != "POSTED":
            blocked_reason = "ACTIVE_PLACEMENT"
        elif len(recent) >= AFFILIATE_COMMENT_MAX_POSTS_PER_24H:
            blocked_reason = "DAILY_LIMIT"
            next_allowed_at = min(
                self._utc_datetime(placement.posted_at or placement.created_at) for placement in recent
            ) + timedelta(hours=24)
        elif posted_history:
            cooldown_until = self._utc_datetime(posted_history[0].posted_at or posted_history[0].created_at) + timedelta(
                hours=AFFILIATE_COMMENT_COOLDOWN_HOURS
            )
            if now < cooldown_until:
                blocked_reason = "COOLDOWN"
                next_allowed_at = cooldown_until
        can_create_another = current is not None and current.status == "POSTED" and len(recent) < AFFILIATE_COMMENT_MAX_POSTS_PER_24H
        return posted_history, {
            "can_create_another": can_create_another,
            "can_post_now": blocked_reason is None,
            "posted_count_24h": len(recent),
            "max_posts_per_24h": AFFILIATE_COMMENT_MAX_POSTS_PER_24H,
            "cooldown_hours": AFFILIATE_COMMENT_COOLDOWN_HOURS,
            "next_allowed_at": next_allowed_at,
            "blocked_reason": blocked_reason,
        }

    @staticmethod
    def _utc_datetime(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)

    def approve_and_enqueue(
        self,
        placement_id: UUID,
        workspace_id: UUID,
        operator_subject: str,
    ) -> tuple[AffiliateCommentPlacement, Job | None, bool]:
        placement = self.db.get(AffiliateCommentPlacement, placement_id)
        if placement is None or placement.workspace_id != workspace_id or not placement.is_current:
            raise AffiliateCommentError("affiliate_comment_not_found", "Affiliate comment placement was not found")
        if placement.status == "POSTED":
            return placement, None, True
        previous_posted_id = str((placement.metadata_json or {}).get("previous_posted_placement_id") or "")
        if previous_posted_id:
            try:
                previous_posted = self.db.get(AffiliateCommentPlacement, UUID(previous_posted_id))
            except ValueError as exc:
                raise AffiliateCommentError(
                    "affiliate_comment_previous_changed",
                    "The previous posted comment reference is invalid; reload this placement",
                ) from exc
            if (
                previous_posted is None
                or previous_posted.workspace_id != workspace_id
                or previous_posted.platform_publication_id != placement.platform_publication_id
                or previous_posted.status != "POSTED"
            ):
                raise AffiliateCommentError(
                    "affiliate_comment_previous_changed",
                    "The previous posted comment changed; reload before approving this comment",
                )
            posted_history, policy = self._another_comment_policy(
                placement.platform_publication_id,
                workspace_id,
                current=previous_posted,
            )
            if not policy["can_post_now"]:
                if policy["blocked_reason"] == "DAILY_LIMIT":
                    raise AffiliateCommentError(
                        "affiliate_comment_daily_limit",
                        "This Reel already has two affiliate comments in the last 24 hours",
                    )
                raise AffiliateCommentError(
                    "affiliate_comment_cooldown",
                    f"Wait until {policy['next_allowed_at'].isoformat()} before posting another affiliate comment",
                )
            if any(item.message_sha256 == placement.message_sha256 for item in posted_history):
                raise AffiliateCommentError(
                    "affiliate_comment_duplicate",
                    "The new affiliate comment must use different content from previously posted comments",
                )
        if (placement.metadata_json or {}).get("template_was_active_at_preview") is False:
            raise AffiliateCommentError(
                "affiliate_comment_template_test_only",
                "This preview uses a test-only template version; regenerate it with an active template before posting",
            )
        self._validate_placement_readiness(placement)
        context = self._load_context(placement.platform_publication_id, workspace_id)
        self._validate_gates(context)
        if context["product_match"].id != placement.affiliate_product_match_id or context["assessment"].id != placement.growth_assessment_id:
            raise AffiliateCommentError("affiliate_comment_gate_changed", "Opportunity gates changed; create a new preview")
        try:
            self.accounts.resolve_config(context["account"].id)
        except PlatformAccountError as exc:
            raise AffiliateCommentError("affiliate_comment_credential_unavailable", str(exc)) from exc
        idempotency_key = f"affiliate-comment-post:{placement.id}:{placement.message_sha256[:24]}"
        existing_job = self.db.get(Job, placement.post_job_id) if placement.post_job_id else None
        if existing_job is not None and existing_job.workspace_id != workspace_id:
            existing_job = None
        if existing_job is None:
            existing_job = self.db.scalar(
                select(Job).where(Job.workspace_id == workspace_id, Job.idempotency_key == idempotency_key)
            )
        if existing_job is not None:
            if existing_job.status in {JobStatus.QUEUED, JobStatus.RUNNING, JobStatus.RETRYABLE}:
                placement.status = "QUEUED"
                placement.post_job_id = existing_job.id
                placement.approved_by = operator_subject[:180]
                placement.approved_at = placement.approved_at or datetime.now(UTC)
                self.db.commit()
                return placement, existing_job, True
            idempotency_key = f"{idempotency_key}:retry:{uuid4().hex[:12]}"
        job = JobService(self.db).create_job(
            workspace_id=workspace_id,
            job_type=JobType.POST_AFFILIATE_COMMENT,
            source_video_id=context["publication"].source_video_id,
            reference_type="affiliate_comment_placement",
            reference_id=placement.id,
            idempotency_key=idempotency_key,
            max_attempts=2,
            payload_json={"affiliate_comment_placement_id": str(placement.id)},
        )
        placement.status = "QUEUED"
        placement.post_job_id = job.id
        placement.approved_by = operator_subject[:180]
        placement.approved_at = datetime.now(UTC)
        placement.metadata_json = {**(placement.metadata_json or {}), "preview_only": False, "operator_approved": True}
        context["publication"].affiliate_comment_status = "QUEUED"
        self.db.commit()
        return placement, job, False

    def execute_job(self, job_id: UUID) -> AffiliateCommentPlacement:
        job = JobService(self.db).get_job(job_id)
        if job.job_type != JobType.POST_AFFILIATE_COMMENT:
            raise AffiliateCommentError("affiliate_comment_job_type_invalid", "Job is not an affiliate comment job")
        placement_id = UUID(str((job.payload_json or {}).get("affiliate_comment_placement_id") or ""))
        placement = self.db.get(AffiliateCommentPlacement, placement_id)
        if placement is None or placement.workspace_id != job.workspace_id or not placement.is_current:
            raise AffiliateCommentError("affiliate_comment_not_found", "Affiliate comment placement was not found")
        if placement.status == "POSTED" and placement.external_comment_id:
            return placement
        context = self._load_context(placement.platform_publication_id, job.workspace_id)
        self._validate_gates(context)
        try:
            config = self.accounts.resolve_config(context["account"].id)
        except PlatformAccountError as exc:
            raise AffiliateCommentError("affiliate_comment_credential_unavailable", str(exc)) from exc
        placement.status = "POSTING"
        context["publication"].affiliate_comment_status = "POSTING"
        self.db.commit()
        try:
            result = FacebookReelsConnector().post_affiliate_comment(
                account=config,
                external_reel_id=placement.external_reel_id,
                message=placement.comment_message,
                attachment_image_url=placement.attachment_image_url,
            )
        except PublishConnectorError as exc:
            FacebookPublishSafetyService(self.db).apply_connector_failure(
                context["account"], error_code=exc.code
            )
            placement.status = "FAILED"
            placement.error_code = exc.code
            placement.error_message = str(exc)
            placement.response_summary_json = exc.response_summary
            context["publication"].affiliate_comment_status = "FAILED"
            self.db.commit()
            raise AffiliateCommentError(exc.code, str(exc)) from exc
        placement.status = "POSTED"
        placement.external_comment_id = result["external_comment_id"]
        placement.external_comment_permalink = result.get("external_comment_permalink")
        placement.response_summary_json = result.get("response_summary")
        placement.posted_at = datetime.now(UTC)
        placement.error_code = None
        placement.error_message = None
        context["publication"].affiliate_comment_status = "POSTED"
        job.result_json = {
            "affiliate_comment_placement_id": str(placement.id),
            "external_comment_id": placement.external_comment_id,
            "has_image_attachment": bool(placement.attachment_image_url),
            "automatic_placement": False,
        }
        self.db.commit()
        # Verification is deliberately separate from posting and never reposts on failure.
        try:
            self._schedule_verification_jobs(placement, job.workspace_id)
        except Exception:
            logger.error(
                "affiliate_comment_verification_schedule_failed",
                extra={"placement_id": str(placement.id), "job_id": str(job.id)},
                exc_info=True,
            )
        self.db.refresh(placement)
        logger.info(
            "affiliate_comment_posted",
            extra={"workspace_id": str(job.workspace_id), "placement_id": str(placement.id), "job_id": str(job.id)},
        )
        return placement

    def _schedule_verification_jobs(self, placement: AffiliateCommentPlacement, workspace_id: UUID) -> None:
        from src.affiliate_intelligence.services.affiliate_comment_verification_service import AffiliateCommentVerificationService

        now = datetime.now(UTC)
        for mode, delay in (("t1m", timedelta(minutes=1)), ("t15m", timedelta(minutes=15)), ("t6h", timedelta(hours=6))):
            AffiliateCommentVerificationService(self.db).enqueue(
                placement.id,
                workspace_id,
                mode=mode,
                scheduled_at=now + delay,
            )
        metadata = dict(placement.metadata_json or {})
        metadata["verification"] = {
            "status": "PENDING",
            "scheduled_checks": ["t1m", "t15m", "t6h"],
        }
        placement.metadata_json = metadata
        self.db.commit()

    def _load_context(self, publication_id: UUID, workspace_id: UUID) -> dict:
        publication = self._publication(publication_id, workspace_id)
        account = self.db.get(PlatformAccount, publication.platform_account_id)
        if account is None or account.workspace_id != workspace_id:
            raise AffiliateCommentError("affiliate_comment_account_not_found", "Facebook Page account was not found")
        product_match = self.db.scalar(
            select(AffiliateProductMatch).where(
                AffiliateProductMatch.workspace_id == workspace_id,
                AffiliateProductMatch.platform_publication_id == publication.id,
                AffiliateProductMatch.is_current.is_(True),
                AffiliateProductMatch.decision_status.in_(["APPROVED", "OVERRIDDEN"]),
                AffiliateProductMatch.selected_product_id.is_not(None),
            )
        )
        if product_match is None:
            raise AffiliateCommentError("affiliate_comment_product_match_required", "Approve a product match before creating a comment preview")
        product = self.db.get(AffiliateProduct, product_match.selected_product_id)
        assessment = self.db.scalar(
            select(PublicationGrowthAssessment).where(
                PublicationGrowthAssessment.workspace_id == workspace_id,
                PublicationGrowthAssessment.platform_publication_id == publication.id,
                PublicationGrowthAssessment.is_current.is_(True),
            )
        )
        if product is None or assessment is None:
            raise AffiliateCommentError("affiliate_comment_opportunity_missing", "A current approved product and Growth Score are required")
        return {"publication": publication, "account": account, "product_match": product_match, "product": product, "assessment": assessment}

    def _validate_gates(self, context: dict) -> None:
        publication = context["publication"]
        account = context["account"]
        product_match = context["product_match"]
        product = context["product"]
        assessment = context["assessment"]
        if publication.platform != PublishTargetPlatform.FACEBOOK_REELS:
            raise AffiliateCommentError("affiliate_comment_platform_unsupported", "Affiliate comments currently support Facebook Reels only")
        if not self._external_reel_id(publication):
            raise AffiliateCommentError("affiliate_comment_external_reel_missing", "Facebook Reel external id is required")
        if account.status != PlatformAccountStatus.ACTIVE or account.is_on_hold:
            raise AffiliateCommentError("affiliate_comment_account_blocked", "Facebook Page is not eligible for an affiliate comment")
        if account.cooldown_until and account.cooldown_until > datetime.now(UTC):
            raise AffiliateCommentError("affiliate_comment_account_cooldown", "Facebook Page is in a safety cooldown")
        metadata = account.metadata_json or {}
        scopes = {str(value) for value in metadata.get("facebook_verified_publish_scopes", [])}
        tasks = {str(value) for value in metadata.get("facebook_page_tasks", [])}
        if metadata.get("facebook_publish_capability_verified") is not True or "pages_manage_posts" not in scopes or "CREATE_CONTENT" not in tasks:
            raise AffiliateCommentError("affiliate_comment_capability_missing", "Facebook Page comment capability is not OAuth-verified")
        if not product.is_active or product.availability_status == "OUT_OF_STOCK":
            raise AffiliateCommentError("affiliate_comment_product_unavailable", "Selected affiliate product is inactive or out of stock")
        self._public_affiliate_url(product.affiliate_url)
        snapshots = list(
            self.db.scalars(
                select(PublicationMetricSnapshot)
                .where(PublicationMetricSnapshot.platform_publication_id == publication.id)
                .order_by(PublicationMetricSnapshot.observed_at.asc(), PublicationMetricSnapshot.id.asc())
            )
        )
        measurement_stale = (
            not snapshots
            or (datetime.now(UTC) - snapshots[-1].observed_at).total_seconds() > STALE_MEASUREMENT_SECONDS
        )
        stale = assessment.input_fingerprint_sha256 != self.growth.input_fingerprint(snapshots) or measurement_stale
        recommendation, _ = self.growth.recommendation(
            growth_score=assessment.growth_score,
            growth_status=assessment.status,
            confidence=assessment.confidence,
            affiliate_fit_score=product_match.selected_fit_score,
            growth_is_stale=stale,
            product_active=product.is_active,
            product_availability=product.availability_status,
        )
        if recommendation != "PRIORITY":
            raise AffiliateCommentError("affiliate_comment_not_priority", "Only a fresh PRIORITY opportunity can receive a Facebook comment")

    def _gate_snapshot(self, context: dict) -> dict:
        return {
            "growth_assessment_id": str(context["assessment"].id),
            "growth_score": context["assessment"].growth_score,
            "growth_confidence": context["assessment"].confidence,
            "affiliate_product_match_id": str(context["product_match"].id),
            "affiliate_fit_score": context["product_match"].selected_fit_score,
            "selected_product_id": str(context["product"].id),
            "attachment_image_url": self._comment_image_url(context["product"].image_url),
            "automatic_placement": False,
        }

    @staticmethod
    def _comment_image_url(value: str | None) -> str | None:
        image_url = str(value or "").strip()
        if not image_url:
            return None
        parsed = urlparse(image_url)
        hostname = str(parsed.hostname or "").lower()
        invalid_host = hostname == "localhost" or hostname.endswith((".localhost", ".local"))
        try:
            address = ip_address(hostname)
        except ValueError:
            address = None
        if parsed.scheme.lower() != "https" or not hostname or invalid_host or (address is not None and not address.is_global):
            raise AffiliateCommentError(
                "affiliate_comment_image_invalid",
                "Product image must use a public HTTPS URL before it can be attached to a Facebook comment",
            )
        return image_url

    @staticmethod
    def _public_affiliate_url(value: str | None) -> str:
        affiliate_url = str(value or "").strip()
        parsed = urlparse(affiliate_url)
        hostname = str(parsed.hostname or "").lower()
        invalid_host = hostname == "localhost" or hostname.endswith((".localhost", ".local"))
        try:
            address = ip_address(hostname)
        except ValueError:
            address = None
        if parsed.scheme.lower() != "https" or not hostname or invalid_host or (address is not None and not address.is_global):
            raise AffiliateCommentError(
                "affiliate_comment_url_invalid",
                "Affiliate URL must use a public HTTPS address; localhost and private network URLs cannot be posted",
            )
        return affiliate_url

    def _validate_placement_readiness(self, placement: AffiliateCommentPlacement) -> None:
        self._public_affiliate_url(placement.affiliate_url)
        self._validate_comment_message(placement.comment_message, placement.affiliate_url)
        if placement.attach_product_image and not placement.attachment_image_url:
            raise AffiliateCommentError(
                "affiliate_comment_image_required",
                "This template requires a product image; add a public image or regenerate with a text-only template",
            )

    @staticmethod
    def _validate_comment_message(message: str, affiliate_url: str) -> None:
        if re.search(r"{{[^{}]+}}", message):
            raise AffiliateCommentError(
                "affiliate_comment_content_unresolved",
                "Comment preview contains an unresolved template placeholder; regenerate it before posting",
            )
        if affiliate_url not in message:
            raise AffiliateCommentError(
                "affiliate_comment_url_missing",
                "The locked affiliate URL must remain in the final comment message",
            )

    @staticmethod
    def _external_reel_id(publication: PlatformPublication) -> str:
        value = publication.external_reel_id or publication.external_publish_id or publication.external_media_id
        if not value:
            raise AffiliateCommentError("affiliate_comment_external_reel_missing", "Facebook Reel external id is required")
        return str(value)

    def _publication(self, publication_id: UUID, workspace_id: UUID) -> PlatformPublication:
        publication = self.db.get(PlatformPublication, publication_id)
        if publication is None or publication.workspace_id != workspace_id:
            raise AffiliateCommentError("affiliate_comment_publication_not_found", "Platform publication was not found")
        return publication
