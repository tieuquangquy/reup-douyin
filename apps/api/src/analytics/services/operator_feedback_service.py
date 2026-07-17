from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import OperatorFeedbackTargetType
from src.models.analytics import OperatorFeedback
from src.models.ingestion import SourceVideo
from src.models.media import RenderOutput
from src.models.publish import PublishAttempt, PublishDraft
from src.schemas.analytics import OperatorFeedbackCreateRequest


class OperatorFeedbackError(ValueError):
    pass


class OperatorFeedbackService:
    def __init__(self, db: Session):
        self.db = db

    def create_feedback(self, request: OperatorFeedbackCreateRequest) -> OperatorFeedback:
        refs = self._resolve_target(request.target_type, request.target_id)
        feedback = OperatorFeedback(
            workspace_id=refs["workspace_id"],
            target_type=request.target_type,
            target_id=request.target_id,
            source_video_id=refs.get("source_video_id"),
            render_output_id=refs.get("render_output_id"),
            publish_draft_id=refs.get("publish_draft_id"),
            publish_attempt_id=refs.get("publish_attempt_id"),
            quality_label=request.quality_label,
            publish_confidence=request.publish_confidence,
            root_cause=request.root_cause,
            note=request.note,
            created_by=request.created_by,
            feedback_at=datetime.now(UTC),
            metadata_json=request.metadata_json,
        )
        self.db.add(feedback)
        self.db.commit()
        self.db.refresh(feedback)
        return feedback

    def list_feedback(
        self,
        *,
        target_type: OperatorFeedbackTargetType | None = None,
        target_id: UUID | None = None,
        source_video_id: UUID | None = None,
        publish_draft_id: UUID | None = None,
        limit: int = 100,
    ) -> list[OperatorFeedback]:
        stmt = select(OperatorFeedback).order_by(OperatorFeedback.feedback_at.desc()).limit(limit)
        if target_type is not None:
            stmt = stmt.where(OperatorFeedback.target_type == target_type)
        if target_id is not None:
            stmt = stmt.where(OperatorFeedback.target_id == target_id)
        if source_video_id is not None:
            stmt = stmt.where(OperatorFeedback.source_video_id == source_video_id)
        if publish_draft_id is not None:
            stmt = stmt.where(OperatorFeedback.publish_draft_id == publish_draft_id)
        return list(self.db.scalars(stmt))

    def _resolve_target(self, target_type: OperatorFeedbackTargetType, target_id: UUID) -> dict:
        if target_type == OperatorFeedbackTargetType.SOURCE_VIDEO:
            source_video = self.db.get(SourceVideo, target_id)
            if source_video is None:
                raise OperatorFeedbackError("source_video_not_found")
            return {"workspace_id": source_video.workspace_id, "source_video_id": source_video.id}

        if target_type == OperatorFeedbackTargetType.RENDER_OUTPUT:
            render = self.db.get(RenderOutput, target_id)
            if render is None:
                raise OperatorFeedbackError("render_output_not_found")
            return {"workspace_id": render.workspace_id, "source_video_id": render.source_video_id, "render_output_id": render.id}

        if target_type == OperatorFeedbackTargetType.PUBLISH_DRAFT:
            draft = self.db.get(PublishDraft, target_id)
            if draft is None:
                raise OperatorFeedbackError("publish_draft_not_found")
            return {
                "workspace_id": draft.workspace_id,
                "source_video_id": draft.source_video_id,
                "render_output_id": draft.render_output_id,
                "publish_draft_id": draft.id,
            }

        if target_type == OperatorFeedbackTargetType.PUBLISH_ATTEMPT:
            attempt = self.db.get(PublishAttempt, target_id)
            if attempt is None:
                raise OperatorFeedbackError("publish_attempt_not_found")
            draft = self.db.get(PublishDraft, attempt.publish_draft_id)
            if draft is None:
                raise OperatorFeedbackError("publish_draft_not_found")
            return {
                "workspace_id": attempt.workspace_id,
                "source_video_id": draft.source_video_id,
                "render_output_id": draft.render_output_id,
                "publish_draft_id": draft.id,
                "publish_attempt_id": attempt.id,
            }

        raise OperatorFeedbackError("unsupported_feedback_target")
