from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.enums import OperatorRiskDecisionType, PublishDraftStatus, PublishTargetPlatform, RenderOutputStatus, RiskTargetType, SourceVideoStatus
from src.models.ingestion import SourceVideo
from src.models.media import RenderOutput
from src.models.publish import PublishDraft
from src.schemas.publish import PublishDraftCreateRequest, PublishDraftScheduleRequest, PublishDraftUpdateRequest
from src.services.publish_draft_helpers import generate_initial_publish_payload, validate_publish_draft_payload
from src.services.publish_targets import get_target_config
from src.risk.services.risk_service import RiskService

logger = logging.getLogger(__name__)


class PublishDraftError(ValueError):
    pass


class PublishDraftService:
    def __init__(self, db: Session):
        self.db = db

    def create_draft(self, request: PublishDraftCreateRequest) -> PublishDraft:
        render = self._resolve_render(request.render_output_id, request.source_video_id)
        source_video = self._load_source_video(render.source_video_id)
        self._assert_publish_ready(source_video, render)
        config = get_target_config(request.target_platform)
        version = self._next_version(source_video.id, config.platform)
        generated = generate_initial_publish_payload(source_video, config)
        draft = PublishDraft(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            render_output_id=render.id,
            target_platform=config.platform.value,
            platform_account_ref=request.platform_account_ref,
            version=version,
            status=PublishDraftStatus.DRAFT,
            title=generated["title"],
            caption=generated["caption"],
            cta_text=generated["cta_text"],
            language_code="vi",
            hashtags_json=generated["hashtags"],
            caption_draft_json={"text": generated["caption"], "source": request.generation_mode},
            cta_draft_json={"text": generated["cta_text"], "source": "platform_default"},
            generation_source=request.generation_mode,
            platform_payload_json={
                "target": {
                    "platform": config.platform.value,
                    "label": config.label,
                    "account_ref": request.platform_account_ref,
                },
                "limits": {
                    "caption_max_length": config.caption_max_length,
                    "hashtag_limit": config.hashtag_limit,
                },
            },
            metadata_json={
                "render_version": render.render_version,
                "render_output_id": str(render.id),
                "source_video_external_id": source_video.source_video_external_id,
            },
        )
        self.db.add(draft)
        self.db.commit()
        self.db.refresh(draft)
        logger.info("publish_draft_created", extra={"publish_draft_id": str(draft.id), "source_video_id": str(source_video.id), "target_platform": draft.target_platform})
        return draft

    def list_drafts(
        self,
        *,
        status: PublishDraftStatus | None = None,
        platform: PublishTargetPlatform | None = None,
        source_video_id: UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PublishDraft]:
        stmt = select(PublishDraft).order_by(PublishDraft.updated_at.desc()).limit(limit).offset(offset)
        if status is not None:
            stmt = stmt.where(PublishDraft.status == status)
        if platform is not None:
            stmt = stmt.where(PublishDraft.target_platform == platform.value)
        if source_video_id is not None:
            stmt = stmt.where(PublishDraft.source_video_id == source_video_id)
        return list(self.db.scalars(stmt))

    def get_draft(self, draft_id: UUID) -> PublishDraft:
        draft = self.db.get(PublishDraft, draft_id)
        if draft is None:
            raise PublishDraftError("Publish draft not found")
        return draft

    def update_draft(self, draft_id: UUID, request: PublishDraftUpdateRequest) -> PublishDraft:
        draft = self.get_draft(draft_id)
        if request.target_platform is not None and request.target_platform.value != draft.target_platform:
            config = get_target_config(request.target_platform)
            draft.target_platform = config.platform.value
            draft.platform_payload_json = {**(draft.platform_payload_json or {}), "target": {"platform": config.platform.value, "label": config.label, "account_ref": request.platform_account_ref or draft.platform_account_ref}}
        for field in ["platform_account_ref", "title", "caption", "cta_text", "language_code", "platform_notes", "scheduling_notes", "notes"]:
            value = getattr(request, field)
            if value is not None:
                setattr(draft, field, value)
        if request.hashtags is not None:
            draft.hashtags_json = [item.model_dump() for item in request.hashtags]
        draft.status = PublishDraftStatus.DRAFT if draft.status == PublishDraftStatus.READY else draft.status
        self.db.commit()
        self.db.refresh(draft)
        logger.info("publish_draft_updated", extra={"publish_draft_id": str(draft.id)})
        return draft

    def schedule_draft(self, draft_id: UUID, request: PublishDraftScheduleRequest) -> PublishDraft:
        draft = self.get_draft(draft_id)
        if request.planned_publish_at <= datetime.now(UTC):
            raise PublishDraftError("planned_publish_at must be in the future")
        draft.planned_publish_at = request.planned_publish_at
        draft.timezone = request.timezone
        draft.scheduled_at = datetime.now(UTC)
        draft.scheduling_notes = request.scheduling_notes
        draft.schedule_json = {
            "planned_publish_at": request.planned_publish_at.isoformat(),
            "timezone": request.timezone,
            "status": "scheduled",
            "scheduler": "phase1_manual_skeleton",
        }
        draft.status = PublishDraftStatus.SCHEDULED
        self.db.commit()
        self.db.refresh(draft)
        logger.info("publish_draft_scheduled", extra={"publish_draft_id": str(draft.id), "planned_publish_at": request.planned_publish_at.isoformat()})
        return draft

    def unschedule_draft(self, draft_id: UUID) -> PublishDraft:
        draft = self.get_draft(draft_id)
        draft.planned_publish_at = None
        draft.scheduled_at = None
        draft.schedule_json = {"status": "unscheduled", "scheduler": "phase1_manual_skeleton"}
        draft.status = PublishDraftStatus.READY if not self.validate_draft(draft) else PublishDraftStatus.DRAFT
        self.db.commit()
        self.db.refresh(draft)
        logger.info("publish_draft_unscheduled", extra={"publish_draft_id": str(draft.id)})
        return draft

    def mark_ready(self, draft_id: UUID) -> PublishDraft:
        draft = self.get_draft(draft_id)
        source_video = self._load_source_video(draft.source_video_id)
        render = self._resolve_render(draft.render_output_id, draft.source_video_id)
        self._assert_publish_ready(source_video, render)
        errors = self.validate_draft(draft)
        if errors:
            raise PublishDraftError("; ".join(errors))
        risk_gate = RiskService(self.db).gate_summary(RiskTargetType.PUBLISH_DRAFT, draft.id)
        if not risk_gate.can_continue:
            raise PublishDraftError("Open critical risk warnings must be resolved or accepted with warning before marking draft ready")
        if risk_gate.requires_operator_decision:
            latest_decision = RiskService(self.db).latest_decision(RiskTargetType.PUBLISH_DRAFT, draft.id)
            if latest_decision is None or latest_decision.decision_type not in {OperatorRiskDecisionType.CONTINUE, OperatorRiskDecisionType.ACCEPT_WITH_WARNING}:
                raise PublishDraftError("High risk warnings require an operator risk decision before marking draft ready")
        draft.status = PublishDraftStatus.READY
        draft.ready_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(draft)
        logger.info("publish_draft_ready", extra={"publish_draft_id": str(draft.id)})
        return draft

    def validate_draft(self, draft: PublishDraft) -> list[str]:
        return validate_publish_draft_payload(draft)

    def _resolve_render(self, render_output_id: UUID | None, source_video_id: UUID | None) -> RenderOutput:
        if render_output_id is not None:
            render = self.db.get(RenderOutput, render_output_id)
        elif source_video_id is not None:
            render = self.db.scalar(
                select(RenderOutput)
                .where(RenderOutput.source_video_id == source_video_id)
                .order_by(RenderOutput.created_at.desc())
                .limit(1)
            )
        else:
            raise PublishDraftError("source_video_id or render_output_id is required")
        if render is None:
            raise PublishDraftError("Approved render output not found")
        return render

    def _load_source_video(self, source_video_id: UUID) -> SourceVideo:
        source_video = self.db.scalar(
            select(SourceVideo).where(SourceVideo.id == source_video_id).options(selectinload(SourceVideo.source_profile))
        )
        if source_video is None:
            raise PublishDraftError("Source video not found")
        return source_video

    def _assert_publish_ready(self, source_video: SourceVideo, render: RenderOutput) -> None:
        if source_video.status != SourceVideoStatus.PUBLISH_READY:
            raise PublishDraftError("Source video must be PUBLISH_READY before creating or readying a publish draft")
        if render.source_video_id != source_video.id:
            raise PublishDraftError("Render output does not belong to source video")
        if render.status != RenderOutputStatus.APPROVED:
            raise PublishDraftError("Render output must be APPROVED before publishing")

    def _next_version(self, source_video_id: UUID, platform: PublishTargetPlatform) -> int:
        max_version = self.db.scalar(
            select(func.max(PublishDraft.version)).where(PublishDraft.source_video_id == source_video_id, PublishDraft.target_platform == platform.value)
        )
        return (max_version or 0) + 1
