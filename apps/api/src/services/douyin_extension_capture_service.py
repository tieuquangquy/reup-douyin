from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import math
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.adapters.douyin import DouyinProfileAdapter
from src.db.bootstrap import ensure_default_workspace
from src.services.capture_inbox_service import CAPTURE_INBOX_ROUTE, CaptureInboxRuntimeError, CaptureInboxService, _float_or_none, _int_or_none, _thumbnail_url_from_payload, _video_id_from_url
from src.models.ingestion import SourceVideo
from src.schemas.douyin_extension import (
    DouyinExtensionCaptureSessionRequest,
    DouyinExtensionCaptureRequest,
    DouyinExtensionDetectPageRequest,
    DouyinExtensionFullModalHarvestRequest,
    DouyinExtensionHarvestPlanRequest,
    DouyinExtensionPageType,
    DouyinExtensionTargetClassificationRequest,
)
from src.services.candidate_types import FilterConfig
from src.services.capture_metadata_normalizer import CaptureMetadataNormalizeInput, CaptureMetadataNormalizer
from src.services.douyin_current_page_capture_service import classify_current_page, current_page_operator_guidance, profile_url_from_current_page
from src.models.capture_inbox import CaptureSession, CapturedItem
from src.enums import CaptureSessionStatus, CapturedItemStatus, SourcePlatformEnum

logger = logging.getLogger(__name__)

EXTENSION_FETCH_PATH = "browser_extension_current_tab"
EXTENSION_CRAWL_MODE = "extension_current_tab_capture"
EXTENSION_STRATEGY_POLICY = "operator_current_tab_extension"
SECRET_KEY_MARKERS = (
    "cookie",
    "authorization",
    "auth_token",
    "csrf",
    "session",
    "password",
    "credential",
    "local_storage",
    "session_storage",
    "browser_profile_path",
)
SUPPORTED_CAPTURE_PAGE_TYPES = {"profile_page", "profile_feed_page", "video_detail_page", "home_feed_page"}


class DouyinExtensionCaptureError(ValueError):
    def __init__(self, code: str, message: str, *, stage: str = "extension_capture", diagnostics_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.diagnostics_id = diagnostics_id


@dataclass(frozen=True)
class DouyinExtensionDetection:
    diagnostics_id: str
    detected_page_type: DouyinExtensionPageType
    supported_capture: bool
    recommended_action: str
    recommended_action_label: str
    operator_message: str
    page_url: str | None
    normalized_profile_url: str | None
    title: str | None
    video_link_count: int
    detected_at: datetime


@dataclass(frozen=True)
class DouyinExtensionCaptureFailureSummary:
    stage: str
    item_index: int | None
    code: str
    message: str


@dataclass(frozen=True)
class DouyinExtensionCaptureSummary:
    success: bool
    diagnostics_id: str
    capture_id: str | None
    detected_page_type: DouyinExtensionPageType
    capture_session_id: UUID | None
    source_profile_id: UUID | None
    crawl_session_id: UUID | None
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    videos_discovered_count: int
    videos_created_count: int
    videos_updated_count: int
    candidates_total_count: int
    candidates_matched_count: int
    candidates_rejected_count: int
    candidate_results_count: int
    captured_item_count: int
    normalized_item_count: int
    duplicate_item_count: int
    ready_item_count: int
    skipped_item_count: int
    promoted_item_count: int
    candidate_created_count: int
    failed_item_count: int
    stage: str
    error_code: str | None
    warning_codes: list[str]
    failure_summaries: list[DouyinExtensionCaptureFailureSummary]
    visible_captured_count: int
    submitted_count: int
    staged_count: int
    deduped_count: int
    skipped_count: int
    failed_count: int
    filters_applied_summary: dict
    unsupported_filters_ignored: list[str]
    fetch_mode: str
    fetch_stage: str | None
    fetch_stage_code: str | None
    fetch_stage_message: str | None
    parser_strategy: str | None
    fetch_execution_path: str | None
    fallback_from_execution_path: str | None
    strategy_policy: str | None
    primary_execution_path: str | None
    http_fallback_attempted: bool | None
    http_fallback_reason: str | None
    preflight_ran: bool
    videos_normalized_count: int
    videos_persisted_count: int
    next_suggested_route: str
    warning: str | None
    discovered_at: datetime
    current_page_url: str | None
    current_page_title: str | None
    current_page_video_link_count: int
    targeted_aweme_one_shot_summary: dict[str, Any]
    scan_summary: dict[str, Any]
    total_found: int
    new_count: int
    incomplete_count: int
    complete_count: int
    target_aweme_ids: list[str]
    new_aweme_ids: list[str]
    incomplete_aweme_ids: list[str]
    complete_aweme_ids: list[str]


@dataclass(frozen=True)
class DouyinExtensionFullModalHarvestSummary:
    success: bool
    ok: bool
    capture_session_id: UUID | None
    capture_inbox_item_id: UUID | None
    source_video_external_id: str | None
    metadata_status: str | None
    item_created_or_updated: bool
    code: str | None
    stage: str | None
    reason: str | None
    capture_session_resolved_by: str | None
    aweme_id: str | None
    target_count: int
    harvested_count: int
    matched_count: int
    updated_count: int
    unchanged_count: int
    failed_count: int
    duration_updated_count: int
    like_updated_count: int
    comment_updated_count: int
    favorite_updated_count: int
    share_updated_count: int
    unmatched_count: int
    flushed_aweme_ids: list[str]
    failure_summaries: list[dict[str, str]]
    stopped_reason: str | None
    accepted_count: int
    rejected_count: int
    created_count: int
    idempotent_unchanged_count: int
    beta_write_effective_status: str
    accepted_unchanged_reason: str | None
    estimated_views_received_count: int
    estimated_views_persisted_count: int
    accepted_not_persisted_count: int
    view_count_null_received_count: int
    real_view_count_data_quality_received_count: int
    estimated_views_accepted_but_not_persisted: str
    finalized_metadata_received_count: int
    finalized_metadata_accepted_count: int
    accepted_not_persisted_fields: list[str]


@dataclass(frozen=True)
class DouyinExtensionCaptureSessionSummary:
    session_id: UUID
    created: bool
    profile_url: str
    source: str
    run_id: str


@dataclass(frozen=True)
class DouyinExtensionHarvestPlanSummary:
    success: bool
    diagnostics_id: str
    plan_id: str
    capture_id: str
    detected_page_type: DouyinExtensionPageType
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    harvest_mode: str
    total_found: int
    new_count: int
    incomplete_count: int
    complete_count: int
    skipped_count: int
    target_count: int
    target_aweme_ids: list[str]
    new_aweme_ids: list[str]
    incomplete_aweme_ids: list[str]
    complete_aweme_ids: list[str]
    skipped_aweme_ids: list[str]
    profile_card_evidence_by_aweme_id: dict[str, Any]
    created_visible_item_count: int
    stage: str
    warning_codes: list[str]
    discovered_at: datetime


class DouyinExtensionCaptureService:
    def __init__(self, db: Session):
        self.db = db

    def create_capture_session(self, request: DouyinExtensionCaptureSessionRequest) -> DouyinExtensionCaptureSessionSummary:
        diagnostics_id = str(uuid4())
        request_dump = request.model_dump(mode="json")
        self._reject_secret_payload(request_dump, diagnostics_id=diagnostics_id, stage="capture_session_preflight")
        existing = self._find_capture_session_by_source_run_id(request.source, request.run_id)
        if existing is not None:
            return DouyinExtensionCaptureSessionSummary(session_id=existing.id, created=False, profile_url=existing.submitted_profile_url or request.profile_url, source=existing.capture_source, run_id=request.run_id)
        workspace = ensure_default_workspace(self.db)
        identity = DouyinProfileAdapter().normalize_profile_identity(request.profile_url)
        now = datetime.now(UTC)
        normalized_profile_url = (request.normalized_profile_url or request.profile_url).strip()
        profile_identifier = request.profile_sec_uid_or_path or identity.source_profile_external_id
        display_title = (request.display_title or "").strip() or None
        profile_display_name = (request.profile_display_name or "").strip() or None
        profile_avatar_url = (request.profile_avatar_url or "").strip() or None
        queued_count = request.queued_count if request.queued_count > 0 else request.verified_target_count
        session_label = display_title or profile_display_name or profile_identifier or request.profile_url
        session = CaptureSession(
            workspace_id=workspace.id,
            capture_id=session_label,
            source_platform=SourcePlatformEnum.DOUYIN,
            capture_source=request.source,
            status=CaptureSessionStatus.RECEIVED,
            detected_page_type="profile_page",
            page_url=normalized_profile_url,
            page_title=display_title,
            submitted_profile_url=request.profile_url,
            normalized_profile_identifier=profile_identifier,
            visible_item_count=0,
            captured_item_count=0,
            normalized_item_count=0,
            started_at=now,
            diagnostics_json={"diagnostics_id": diagnostics_id, "source": request.source, "mode": request.mode, "stage": "capture_session_create"},
            metadata_json={
                "schema_version": request.schema_version,
                "capture_model": f"{request.source}_session_preflight",
                "review_boundary": "capture_inbox_before_review_board",
                "stage": "canonical_capture_session_created" if request.source == "whole_profile_harvest" else "v2_capture_session_created",
                "run_id": request.run_id,
                "source": request.source,
                "mode": request.mode,
                "profile_url": request.profile_url,
                "normalized_profile_url": normalized_profile_url,
                "profile_sec_uid_or_path": request.profile_sec_uid_or_path,
                "normalized_profile_identifier": profile_identifier,
                "profile_display_name": profile_display_name,
                "profile_avatar_url": profile_avatar_url,
                "display_title": display_title,
                "expected_video_count": request.verified_target_count,
                "queued_count": queued_count,
                "collection_mode": request.mode,
                "created_by": "douyin_scanner",
                "source_modal_aweme_id": request.source_modal_aweme_id,
                "verified_target_count": request.verified_target_count,
            },
            raw_summary_json={"verified_target_count": request.verified_target_count, "expected_video_count": request.verified_target_count, "queued_count": queued_count, "visible_item_count": 0},
            result_summary_json={"items_created_by_preflight": 0},
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        logger.info(
            "douyin_extension_capture_session_created",
            extra={"diagnostics_id": diagnostics_id, "capture_session_id": str(session.id), "run_id": request.run_id, "source": request.source},
        )
        return DouyinExtensionCaptureSessionSummary(session_id=session.id, created=True, profile_url=request.profile_url, source=request.source, run_id=request.run_id)

    def detect_page(self, request: DouyinExtensionDetectPageRequest) -> DouyinExtensionDetection:
        diagnostics_id = str(uuid4())
        self._reject_secret_payload(request.model_dump(mode="json"), diagnostics_id=diagnostics_id, stage="detect_page")
        page = request.page
        detected_page_type = self._resolve_page_type(
            page_type=page.page_type,
            page_url=page.url,
            title=page.title,
            body_text=page.body_text_sample,
            video_link_count=page.video_link_count,
        )
        normalized_profile_url = self._resolve_profile_url(request, detected_page_type=detected_page_type)
        supported_capture = detected_page_type in SUPPORTED_CAPTURE_PAGE_TYPES and normalized_profile_url is not None
        action, label, message = extension_page_operator_guidance(detected_page_type, supported_capture=supported_capture)
        logger.info(
            "douyin_extension_page_detected",
            extra={
                "diagnostics_id": diagnostics_id,
                "detected_page_type": detected_page_type,
                "supported_capture": supported_capture,
                "video_link_count": page.video_link_count,
            },
        )
        return DouyinExtensionDetection(
            diagnostics_id=diagnostics_id,
            detected_page_type=detected_page_type,
            supported_capture=supported_capture,
            recommended_action=action,
            recommended_action_label=label,
            operator_message=message,
            page_url=page.url,
            normalized_profile_url=normalized_profile_url,
            title=page.title,
            video_link_count=page.video_link_count,
            detected_at=datetime.now(UTC),
        )

    def create_harvest_plan(self, request: DouyinExtensionHarvestPlanRequest) -> DouyinExtensionHarvestPlanSummary:
        diagnostics_id = str(uuid4())
        self._reject_secret_payload(request.model_dump(mode="json"), diagnostics_id=diagnostics_id, stage="harvest_plan")
        detected_page_type = self._resolve_page_type(
            page_type=request.page.page_type,
            page_url=request.page.url,
            title=request.page.title,
            body_text=request.page.body_text_sample,
            video_link_count=request.page.video_link_count,
        )
        profile_url = self._resolve_profile_url(request, detected_page_type=detected_page_type) or request.page.url or "https://www.douyin.com/"
        identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
        summary = self._build_harvest_plan_summary(request.videos, harvest_mode=request.harvest_mode)
        evidence_by_aweme_id = self._profile_card_evidence_by_aweme_id(request.videos)
        logger.info(
            "douyin_extension_harvest_plan_created",
            extra={
                "diagnostics_id": diagnostics_id,
                "capture_id": request.capture_id,
                "detected_page_type": detected_page_type,
                "total_found": summary["total_found"],
                "target_count": summary["target_count"],
                "harvest_mode": summary["harvest_mode"],
            },
        )
        return DouyinExtensionHarvestPlanSummary(
            success=True,
            diagnostics_id=diagnostics_id,
            plan_id=f"harvest-plan:{request.capture_id}",
            capture_id=request.capture_id,
            detected_page_type=detected_page_type,
            submitted_profile_url=profile_url,
            normalized_profile_identifier=identity.source_profile_external_id,
            harvest_mode=summary["harvest_mode"],
            total_found=summary["total_found"],
            new_count=summary["new_count"],
            incomplete_count=summary["incomplete_count"],
            complete_count=summary["complete_count"],
            skipped_count=summary["skipped_count"],
            target_count=summary["target_count"],
            target_aweme_ids=summary["target_aweme_ids"],
            new_aweme_ids=summary["new_aweme_ids"],
            incomplete_aweme_ids=summary["incomplete_aweme_ids"],
            complete_aweme_ids=summary["complete_aweme_ids"],
            skipped_aweme_ids=summary["skipped_aweme_ids"],
            profile_card_evidence_by_aweme_id=evidence_by_aweme_id,
            created_visible_item_count=0,
            stage="harvest_plan_created",
            warning_codes=[],
            discovered_at=datetime.now(UTC),
        )

    def classify_targets(self, request: DouyinExtensionTargetClassificationRequest) -> dict[str, Any]:
        diagnostics_id = str(uuid4())
        payload = request.model_dump(mode="json")
        self._reject_secret_payload(payload, diagnostics_id=diagnostics_id, stage="classify_targets")

        status_order = ["new", "incomplete", "complete", "failed", "skipped", "unknown"]
        counts: dict[str, int] = {key: 0 for key in status_order}
        items: list[dict[str, Any]] = []

        for target in request.targets:
            aweme_id = str(target.source_video_external_id or target.aweme_id or "").strip()
            if not aweme_id:
                counts["unknown"] += 1
                items.append(
                    {
                        "aweme_id": str(target.aweme_id or ""),
                        "source_video_external_id": "",
                        "capture_status": "unknown",
                        "item_id": None,
                        "metadata_status": "missing_aweme_id",
                        "missing_fields": ["source_video_external_id"],
                        "existing_fields": {},
                        "updated_at": None,
                    }
                )
                continue

            existing = self.db.scalar(
                select(SourceVideo).where(
                    SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                    SourceVideo.source_video_external_id == aweme_id,
                )
            )
            if existing is None:
                capture_status = "new"
                missing_fields = ["source_video"]
                existing_fields: dict[str, bool] = {}
                metadata_status = "missing"
                item_id = None
                updated_at = None
            else:
                metadata = getattr(existing, "metadata_json", None)
                metadata = metadata if isinstance(metadata, dict) else {}
                existing_fields = {
                    "duration_seconds": getattr(existing, "duration_seconds", None) is not None,
                    "posted_at": getattr(existing, "posted_at", None) is not None or bool(str(metadata.get("posted_text") or "").strip()),
                    "like_count": _int_or_none(metadata.get("like_count")) is not None,
                    "comment_count": _int_or_none(metadata.get("comment_count")) is not None,
                    "favorite_count": _int_or_none(metadata.get("favorite_count")) is not None,
                    "share_count": _int_or_none(metadata.get("share_count")) is not None,
                }
                missing_fields = [name for name, has_value in existing_fields.items() if not has_value]
                is_complete = isDouyinCaptureItemMetadataComplete(existing)
                capture_status = "complete" if is_complete else "incomplete"
                metadata_status = "complete" if is_complete else "incomplete"
                item_id = getattr(existing, "id", None)
                updated_at = getattr(existing, "updated_at", None)

            counts[capture_status] += 1
            items.append(
                {
                    "aweme_id": aweme_id,
                    "source_video_external_id": aweme_id,
                    "capture_status": capture_status,
                    "item_id": item_id,
                    "metadata_status": metadata_status,
                    "missing_fields": missing_fields,
                    "existing_fields": existing_fields,
                    "updated_at": updated_at,
                }
            )

        logger.info(
            "douyin_extension_target_classification_completed",
            extra={
                "diagnostics_id": diagnostics_id,
                "profile_url": request.profile_url,
                "target_count": len(request.targets),
                "counts": counts,
            },
        )
        return {"ok": True, "profile_url": request.profile_url, "items": items, "counts": counts}

    def capture_current_page(
        self,
        request: DouyinExtensionCaptureRequest,
        *,
        filter_config: FilterConfig | None,
    ) -> DouyinExtensionCaptureSummary:
        diagnostics_id = str(uuid4())
        stage = "validate_extension_payload"
        payload_dump = request.model_dump(mode="json")
        self._reject_secret_payload(payload_dump, diagnostics_id=diagnostics_id, stage=stage)
        detected_page_type = self._resolve_page_type(
            page_type=request.page.page_type,
            page_url=request.page.url,
            title=request.page.title,
            body_text=request.page.body_text_sample,
            video_link_count=request.page.video_link_count or len(request.videos),
        )
        if detected_page_type in {"login_page", "challenge_page", "unsupported_page", "unknown_page"}:
            action, _, message = extension_page_operator_guidance(detected_page_type, supported_capture=False)
            raise DouyinExtensionCaptureError(
                f"extension_{detected_page_type}_not_capturable",
                f"{message} Recommended action: {action}.",
                stage="classify_extension_page",
                diagnostics_id=diagnostics_id,
            )
        profile_url = self._resolve_profile_url(request, detected_page_type=detected_page_type)
        if profile_url is None:
            raise DouyinExtensionCaptureError(
                "extension_profile_url_missing",
                "The extension payload did not include a supported Douyin profile URL. Open a profile page or capture visible items that include profile ownership hints.",
                stage="resolve_profile_url",
                diagnostics_id=diagnostics_id,
            )
        thumbnail_payload_count = sum(1 for video in request.videos if video.thumbnail_url or video.cover_url or video.poster_url or video.url_list)
        logger.info(
            "douyin_extension_card_grid_payload_received",
            extra={
                "diagnostics_id": diagnostics_id,
                "capture_id": request.capture_id,
                "detected_page_type": detected_page_type,
                "video_count": len(request.videos),
                "thumbnail_payload_count": thumbnail_payload_count,
                "preview_status_counts": _status_counts(video.preview_status or "missing" for video in request.videos),
                "source_link_status_counts": _status_counts(video.source_link_status or "missing" for video in request.videos),
                "media_asset_status_counts": _status_counts(video.media_asset_status or "not_generated" for video in request.videos),
                "network_metadata_payload_count": sum(1 for video in request.videos if video.network_source),
                "poster_aspect_ratio_payload_count": sum(1 for video in request.videos if video.poster_aspect_ratio is not None),
                "duration_payload_count": sum(1 for video in request.videos if video.duration_seconds is not None or video.duration_text),
                "posted_payload_count": sum(1 for video in request.videos if video.posted_at is not None or video.posted_text),
                "view_count_payload_count": sum(1 for video in request.videos if video.view_count is not None or video.view_count_text),
                "like_count_payload_count": sum(1 for video in request.videos if video.like_count is not None or video.like_count_text),
                "comment_count_payload_count": sum(1 for video in request.videos if video.comment_count is not None or video.comment_count_text),
                "extension_thumbnail_candidate_video_count": request.diagnostics.get("thumbnail_candidate_video_count"),
                "extension_thumbnail_candidate_total_count": request.diagnostics.get("thumbnail_candidate_total_count"),
                "extension_thumbnail_source_types": request.diagnostics.get("thumbnail_source_types"),
                "extension_duration_text_video_count": request.diagnostics.get("duration_text_video_count"),
                "extension_posted_text_video_count": request.diagnostics.get("posted_text_video_count"),
                "extension_view_count_video_count": request.diagnostics.get("view_count_video_count"),
                "extension_like_count_video_count": request.diagnostics.get("like_count_video_count"),
                "extension_comment_count_video_count": request.diagnostics.get("comment_count_video_count"),
            },
        )
        if detected_page_type != "video_detail_page" and not request.videos:
            logger.info(
                "douyin_extension_zero_visible_videos",
                extra={"diagnostics_id": diagnostics_id, "capture_id": request.capture_id, "detected_page_type": detected_page_type},
            )

        try:
            stage_result = CaptureInboxService(self.db).stage_extension_capture(
                request,
                diagnostics_id=diagnostics_id,
                detected_page_type=detected_page_type,
                profile_url=profile_url,
                safe_diagnostics=self._safe_diagnostics(request.diagnostics),
            )
        except CaptureInboxRuntimeError as exc:
            logger.error(
                "douyin_extension_capture_runtime_failure",
                extra={
                    "diagnostics_id": diagnostics_id,
                    "error_code": exc.code,
                    "stage": exc.stage,
                    "capture_id": request.capture_id,
                    "detected_page_type": detected_page_type,
                },
            )
            raise DouyinExtensionCaptureError(exc.code, exc.message, stage=exc.stage, diagnostics_id=diagnostics_id) from exc
        session = stage_result.session
        response_thumbnail_count = sum(1 for item in stage_result.items if getattr(item, "thumbnail_url", None))
        logger.info(
            "douyin_extension_card_grid_payload_staged",
            extra={
                "diagnostics_id": diagnostics_id,
                "capture_id": request.capture_id,
                "capture_session_id": str(session.id),
                "detected_page_type": detected_page_type,
                "captured_item_count": session.captured_item_count,
                "thumbnail_item_count": response_thumbnail_count,
                "preview_ready_count": sum(1 for item in stage_result.items if getattr(item, "preview_ready", False)),
                "media_ready_count": sum(1 for item in stage_result.items if getattr(item, "media_ready", False)),
                "preview_status_counts": _status_counts((getattr(item, "metadata_json", None) or {}).get("preview_status") for item in stage_result.items),
                "source_link_status_counts": _status_counts((getattr(item, "metadata_json", None) or {}).get("source_link_status") for item in stage_result.items),
                "media_asset_status_counts": _status_counts((getattr(item, "metadata_json", None) or {}).get("media_asset_status") for item in stage_result.items),
                "source_link_captured_count": sum(1 for item in stage_result.items if (getattr(item, "metadata_json", None) or {}).get("source_link_status") == "captured"),
            },
        )
        fetch_stage_code = "staged" if session.captured_item_count > 0 else "true_zero_videos"
        fetch_stage_message = (
            "Extension current-tab capture was staged in Capture Inbox. Promote ready items from the inbox before Review Board review."
            if session.captured_item_count > 0
            else "Extension current-tab capture completed, but no visible videos were staged. Scroll/load more manually and capture again."
        )
        warning = None
        if session.captured_item_count == 0:
            warning = "No visible videos were staged from the current tab. Scroll/load more manually and capture again."
        elif session.ready_item_count == 0:
            warning = "Capture was staged, but no items are ready for promotion yet. Open Capture Inbox to inspect missing fields."

        failure_summaries = [
            DouyinExtensionCaptureFailureSummary(
                stage=failure.stage,
                item_index=failure.item_index,
                code=failure.code,
                message=failure.message,
            )
            for failure in stage_result.failure_summaries
        ]
        stage = stage_result.stage
        if session.failed_item_count and session.failed_item_count == session.captured_item_count and session.captured_item_count > 0:
            stage = "item_normalization_partial_failure"
        targeted_summaries_map = {}
        session_result_summary = getattr(session, "result_summary_json", None)
        if isinstance(session_result_summary, dict):
            candidate_map = session_result_summary.get("targeted_aweme_one_shot_summaries")
            if isinstance(candidate_map, dict):
                targeted_summaries_map = {str(key): value for key, value in candidate_map.items() if isinstance(value, dict)}
        targeted_summary_payload = {
            "items": [targeted_summaries_map[aweme_id] for aweme_id in sorted(targeted_summaries_map.keys())],
        }
        if targeted_summary_payload["items"]:
            targeted_summary_log_payload = {"targeted_aweme_one_shot_summary": targeted_summary_payload}
            logger.info(
                "targeted_aweme_one_shot_summary_full\n%s",
                json.dumps(targeted_summary_log_payload, ensure_ascii=False, indent=2),
                extra={
                    "diagnostics_id": diagnostics_id,
                    "capture_id": request.capture_id,
                    "capture_session_id": str(session.id),
                    "aweme_ids": [item.get("aweme_id") for item in targeted_summary_payload["items"]],
                    "targeted_aweme_one_shot_summary": targeted_summary_payload,
                },
            )

        scan_summary = self._build_incremental_scan_summary(stage_result.items, harvest_mode=request.harvest_mode)
        session.result_summary_json = {
            **(getattr(session, "result_summary_json", None) or {}),
            "incremental_scan_summary": scan_summary,
        }
        if hasattr(self.db, "commit"):
            self.db.commit()

        return DouyinExtensionCaptureSummary(
            success=True,
            diagnostics_id=diagnostics_id,
            capture_id=request.capture_id,
            detected_page_type=detected_page_type,
            capture_session_id=session.id,
            source_profile_id=None,
            crawl_session_id=None,
            submitted_profile_url=profile_url,
            normalized_profile_identifier=session.normalized_profile_identifier,
            videos_discovered_count=session.visible_item_count,
            videos_created_count=0,
            videos_updated_count=0,
            candidates_total_count=0,
            candidates_matched_count=0,
            candidates_rejected_count=0,
            candidate_results_count=0,
            captured_item_count=session.captured_item_count,
            normalized_item_count=session.normalized_item_count,
            duplicate_item_count=session.duplicate_item_count,
            ready_item_count=session.ready_item_count,
            skipped_item_count=session.skipped_item_count,
            promoted_item_count=session.promoted_item_count,
            candidate_created_count=session.candidate_created_count,
            failed_item_count=session.failed_item_count,
            stage=stage,
            error_code=None,
            warning_codes=stage_result.warning_codes,
            failure_summaries=failure_summaries,
            visible_captured_count=session.visible_item_count,
            submitted_count=len(request.videos),
            staged_count=session.captured_item_count,
            deduped_count=session.duplicate_item_count,
            skipped_count=session.skipped_item_count,
            failed_count=session.failed_item_count,
            filters_applied_summary=filter_config.to_dict() if filter_config is not None else {},
            unsupported_filters_ignored=[],
            fetch_mode=EXTENSION_CRAWL_MODE,
            fetch_stage="extension_current_tab_capture",
            fetch_stage_code=fetch_stage_code,
            fetch_stage_message=fetch_stage_message,
            parser_strategy="extension_visible_dom_v1",
            fetch_execution_path=EXTENSION_FETCH_PATH,
            fallback_from_execution_path=None,
            strategy_policy=EXTENSION_STRATEGY_POLICY,
            primary_execution_path=EXTENSION_FETCH_PATH,
            http_fallback_attempted=False,
            http_fallback_reason=None,
            preflight_ran=False,
            videos_normalized_count=session.normalized_item_count,
            videos_persisted_count=session.captured_item_count,
            next_suggested_route=CAPTURE_INBOX_ROUTE,
            warning=warning,
            discovered_at=datetime.now(UTC),
            current_page_url=request.page.url,
            current_page_title=request.page.title,
            current_page_video_link_count=request.page.video_link_count,
            targeted_aweme_one_shot_summary=targeted_summary_payload,
            scan_summary=scan_summary,
            total_found=scan_summary["total_found"],
            new_count=scan_summary["new_count"],
            incomplete_count=scan_summary["incomplete_count"],
            complete_count=scan_summary["complete_count"],
            target_aweme_ids=scan_summary["target_aweme_ids"],
            new_aweme_ids=scan_summary["new_aweme_ids"],
            incomplete_aweme_ids=scan_summary["incomplete_aweme_ids"],
            complete_aweme_ids=scan_summary["complete_aweme_ids"],
        )

    def ingest_full_modal_harvest(self, request: DouyinExtensionFullModalHarvestRequest) -> DouyinExtensionFullModalHarvestSummary:
        diagnostics_id = str(uuid4())
        request_dump = request.model_dump(mode="json")
        request_dump.pop("capture_session_id", None)
        request_dump.pop("capture_session_source", None)
        self._reject_secret_payload(request_dump, diagnostics_id=diagnostics_id, stage="full_modal_harvest_ingest")
        logger.info(
            "full_modal_harvest_received",
            extra={
                "diagnostics_id": diagnostics_id,
                "capture_session_id": str(request.capture_session_id) if request.capture_session_id else None,
                "submitted_item_count": len(request.items),
                "target_count": request.progress.target_count,
                "harvested_count": request.progress.harvested_count,
                "stopped_reason": request.progress.stopped_reason,
            },
        )
        capture_session = self._resolve_capture_session_for_harvest(request)
        existing_items = [item for item in capture_session.items if item.source_video_external_id]
        by_aweme_id = {str(item.source_video_external_id).strip(): item for item in existing_items if item.source_video_external_id}

        matched_count = 0
        updated_count = 0
        unchanged_count = 0
        failed_count = 0
        unmatched_count = 0
        duration_updated_count = 0
        like_updated_count = 0
        comment_updated_count = 0
        favorite_updated_count = 0
        share_updated_count = 0
        estimated_views_received_count = sum(1 for payload in request.items if payload.estimated_views is not None)
        view_count_null_received_count = sum(1 for payload in request.items if payload.view_count is None and "view_count" in payload.model_fields_set)
        real_view_count_data_quality_received_count = sum(1 for payload in request.items if payload.real_view_count_data_quality is not None)
        finalized_metadata_received_count = sum(1 for payload in request.items if self._is_finalized_modal_payload(payload))
        estimated_views_accepted_count = 0
        estimated_views_persisted_count = 0
        finalized_metadata_accepted_count = 0

        inbox_service = CaptureInboxService(self.db)
        updated_items: list[CapturedItem] = []
        flushed_aweme_ids: list[str] = []
        failure_summaries: list[dict[str, str]] = []
        last_processed_aweme_id: str | None = None
        resolved_by = "explicit_capture_session_id" if request.capture_session_id is not None else "latest_active_session"
        if request.capture_session_source == "whole_profile_staged_harvest_v2" and request.run_id:
            resolved_by = "v2_run_id"

        for payload in request.items:
            aweme_id = payload.aweme_id.strip()
            last_processed_aweme_id = aweme_id
            raw_metrics = payload.raw_dom_detail_metrics
            identity_map = {
                "payload_aweme_id": aweme_id,
                "source_video_external_id": (payload.source_video_external_id or "").strip() or None,
                "target_aweme_id": (payload.target_aweme_id or "").strip() or None,
                "modal_aweme_id_before_extract": (payload.modal_aweme_id_before_extract or "").strip() or None,
                "modal_aweme_id_after_extract": (payload.modal_aweme_id_after_extract or "").strip() or None,
                "extracted_aweme_id": (payload.extracted_aweme_id or "").strip() or None,
                "raw_dom_detail_metrics_target_aweme_id": (raw_metrics.target_aweme_id or "").strip() or None,
                "raw_dom_detail_metrics_aweme_id": (raw_metrics.aweme_id or "").strip() or None,
            }
            mismatch_fields = [
                field
                for field, value in identity_map.items()
                if field != "payload_aweme_id" and value is not None and value != aweme_id
            ]
            item = by_aweme_id.get(aweme_id)
            item_platform = getattr(item, "source_platform", SourcePlatformEnum.DOUYIN) if item is not None else None
            if item is not None and item_platform != SourcePlatformEnum.DOUYIN:
                mismatch_fields.append("source_platform")
            logger.info(
                "full_modal_harvest_matched",
                extra={
                    "diagnostics_id": diagnostics_id,
                    "capture_session_id": str(capture_session.id),
                    "aweme_id": aweme_id,
                    "matched": item is not None,
                    "existing_item_id": str(item.id) if item is not None else None,
                    "data_integrity_status": payload.data_integrity_status,
                    "mismatch_fields": mismatch_fields,
                },
            )
            if payload.data_integrity_status in {"mismatch", "failed"} or mismatch_fields:
                failed_count += 1
                failure_summaries.append(
                    {
                        "aweme_id": aweme_id,
                        "reason": "data_integrity_mismatch",
                        "data_integrity_status": payload.data_integrity_status or "failed",
                        "mismatch_fields": ",".join(mismatch_fields) if mismatch_fields else "payload_reported_mismatch",
                    }
                )
                flushed_aweme_ids.append(aweme_id)
                continue
            if item is None and request.commit_policy == "finalized_only":
                if not self._is_finalized_modal_payload(payload):
                    failed_count += 1
                    failure_summaries.append({"aweme_id": aweme_id, "reason": "finalized_metadata_required"})
                    flushed_aweme_ids.append(aweme_id)
                    continue
                item = self._create_finalized_harvest_item(capture_session, payload, raw_item_index=len(capture_session.items) + len(updated_items))
                finalized_metadata_accepted_count += 1
                by_aweme_id[aweme_id] = item
            elif item is None:
                unmatched_count += 1
                flushed_aweme_ids.append(aweme_id)
                continue
            matched_count += 1
            if payload.estimated_views is not None:
                estimated_views_accepted_count += 1
            try:
                update_result = self._apply_modal_harvest_to_item(item, payload)
                estimated_views_persisted_count += int(update_result.get("estimated_views_persisted", False))
            except Exception as exc:  # noqa: BLE001
                failed_count += 1
                failure_summaries.append({"aweme_id": aweme_id, "reason": str(exc) or "full_modal_harvest_item_failed"})
                continue
            flushed_aweme_ids.append(aweme_id)
            if update_result["updated"]:
                updated_count += 1
                duration_updated_count += int(update_result["duration_updated"])
                like_updated_count += int(update_result["like_updated"])
                comment_updated_count += int(update_result["comment_updated"])
                favorite_updated_count += int(update_result["favorite_updated"])
                share_updated_count += int(update_result["share_updated"])
                updated_items.append(item)
            else:
                unchanged_count += 1

        if updated_items:
            inbox_service._evaluate_items_against_intake(updated_items, session=capture_session)
            inbox_service._reconcile_session(capture_session)
            self.db.commit()
        elif matched_count > 0:
            inbox_service._reconcile_session(capture_session)
            self.db.commit()

        logger.info(
            "douyin_extension_full_modal_harvest_ingested",
            extra={
                "diagnostics_id": diagnostics_id,
                "capture_session_id": str(capture_session.id),
                "submitted_item_count": len(request.items),
                "matched_count": matched_count,
                "updated_count": updated_count,
                "unmatched_count": unmatched_count,
                "stopped_reason": request.progress.stopped_reason,
            },
        )
        response_item = updated_items[-1] if updated_items else next((item for item in existing_items if str(getattr(item, "source_video_external_id", "")).strip() in flushed_aweme_ids), None)
        response_metadata = getattr(response_item, "metadata_json", None) if response_item is not None else None
        response_metadata_status = response_metadata.get("metadata_status") if isinstance(response_metadata, dict) else None
        item_created_or_updated = bool(updated_items)
        idempotent_unchanged_count = unchanged_count if matched_count > 0 and failed_count == 0 and unmatched_count == 0 and updated_count == 0 and unchanged_count == matched_count else 0
        accepted_unchanged_reason = "accepted_payload_already_matched_persisted_values" if idempotent_unchanged_count > 0 else None
        response_code = None
        response_stage = "full_modal_harvest_ingest"
        response_reason = accepted_unchanged_reason
        metadata_json = getattr(capture_session, "metadata_json", None)
        metadata = metadata_json if isinstance(metadata_json, dict) else {}
        existing_events = metadata.get("last_ingest_events") if isinstance(metadata.get("last_ingest_events"), list) else []
        event = {
            "time": datetime.now(UTC).isoformat(),
            "aweme_id": last_processed_aweme_id,
            "stage": response_stage,
            "status": "ok" if item_created_or_updated or idempotent_unchanged_count > 0 else "failed",
            "item_created_or_updated": item_created_or_updated,
            "idempotent_unchanged_count": idempotent_unchanged_count,
            "capture_inbox_item_id": str(getattr(response_item, "id", "")) if response_item is not None else None,
            "error_code": response_code,
        }
        capture_session.metadata_json = {
            **metadata,
            "last_ingest_events": (existing_events + [event])[-20:],
        }

        accepted_count = matched_count + unmatched_count
        rejected_count = failed_count
        created_count = finalized_metadata_accepted_count
        write_ok = failed_count == 0 and (updated_count > 0 or idempotent_unchanged_count > 0 or created_count > 0)
        beta_write_effective_status = "updated_success" if updated_count > 0 or created_count > 0 else "idempotent_success" if idempotent_unchanged_count > 0 else "failed"
        accepted_not_persisted_fields = []
        if estimated_views_accepted_count > estimated_views_persisted_count:
            accepted_not_persisted_fields.append("estimated_views")
        accepted_not_persisted_count = max(estimated_views_accepted_count - estimated_views_persisted_count, 0)

        return DouyinExtensionFullModalHarvestSummary(
            success=write_ok,
            ok=write_ok,
            capture_session_id=capture_session.id,
            capture_inbox_item_id=getattr(response_item, "id", None),
            source_video_external_id=getattr(response_item, "source_video_external_id", None) if response_item is not None else None,
            metadata_status=response_metadata_status if isinstance(response_metadata_status, str) else None,
            item_created_or_updated=item_created_or_updated,
            code=response_code,
            stage=response_stage,
            reason=response_reason,
            capture_session_resolved_by=resolved_by,
            aweme_id=last_processed_aweme_id,
            target_count=request.progress.target_count,
            harvested_count=request.progress.harvested_count,
            matched_count=matched_count,
            updated_count=updated_count,
            unchanged_count=unchanged_count,
            failed_count=failed_count,
            duration_updated_count=duration_updated_count,
            like_updated_count=like_updated_count,
            comment_updated_count=comment_updated_count,
            favorite_updated_count=favorite_updated_count,
            share_updated_count=share_updated_count,
            unmatched_count=unmatched_count,
            flushed_aweme_ids=flushed_aweme_ids,
            failure_summaries=failure_summaries,
            stopped_reason=request.progress.stopped_reason,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            created_count=created_count,
            idempotent_unchanged_count=idempotent_unchanged_count,
            beta_write_effective_status=beta_write_effective_status,
            accepted_unchanged_reason=accepted_unchanged_reason,
            estimated_views_received_count=estimated_views_received_count,
            estimated_views_persisted_count=estimated_views_persisted_count,
            accepted_not_persisted_count=accepted_not_persisted_count,
            view_count_null_received_count=view_count_null_received_count,
            real_view_count_data_quality_received_count=real_view_count_data_quality_received_count,
            estimated_views_accepted_but_not_persisted="yes" if "estimated_views" in accepted_not_persisted_fields else "no",
            finalized_metadata_received_count=finalized_metadata_received_count,
            finalized_metadata_accepted_count=finalized_metadata_accepted_count,
            accepted_not_persisted_fields=accepted_not_persisted_fields,
        )

    def _build_incremental_scan_summary(self, items: list[CapturedItem], *, harvest_mode: str = "new_and_incomplete") -> dict[str, Any]:
        seen: set[str] = set()
        captured_aweme_ids: list[str] = []
        new_aweme_ids: list[str] = []
        incomplete_aweme_ids: list[str] = []
        complete_aweme_ids: list[str] = []
        skipped_aweme_ids: list[str] = []
        effective_mode = harvest_mode if harvest_mode in {"new_only", "new_and_incomplete", "refresh_all"} else "new_and_incomplete"
        for item in items:
            aweme_id = str(getattr(item, "source_video_external_id", None) or "").strip()
            if not aweme_id or aweme_id in seen:
                if aweme_id:
                    skipped_aweme_ids.append(aweme_id)
                continue
            seen.add(aweme_id)
            captured_aweme_ids.append(aweme_id)
            if getattr(item, "status", None) == CapturedItemStatus.DUPLICATE and getattr(item, "existing_source_video_id", None) is None:
                skipped_aweme_ids.append(aweme_id)
                continue
            existing = self.db.scalar(
                select(SourceVideo).where(
                    SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                    SourceVideo.source_video_external_id == aweme_id,
                )
            )
            if existing is None:
                new_aweme_ids.append(aweme_id)
            elif isDouyinCaptureItemMetadataComplete(existing):
                complete_aweme_ids.append(aweme_id)
            else:
                incomplete_aweme_ids.append(aweme_id)
        if effective_mode == "refresh_all":
            target_aweme_ids = captured_aweme_ids
        elif effective_mode == "new_only":
            target_aweme_ids = new_aweme_ids
        else:
            target_aweme_ids = new_aweme_ids + incomplete_aweme_ids
        return {
            "harvest_mode": effective_mode,
            "total_found": len(seen),
            "new_count": len(new_aweme_ids),
            "incomplete_count": len(incomplete_aweme_ids),
            "complete_count": len(complete_aweme_ids),
            "skipped_count": len(skipped_aweme_ids),
            "target_count": len(target_aweme_ids),
            "target_aweme_ids": target_aweme_ids,
            "new_aweme_ids": new_aweme_ids,
            "incomplete_aweme_ids": incomplete_aweme_ids,
            "complete_aweme_ids": complete_aweme_ids,
            "skipped_aweme_ids": skipped_aweme_ids,
        }

    def _resolve_capture_session_for_harvest(self, request: DouyinExtensionFullModalHarvestRequest) -> CaptureSession:
        inbox_service = CaptureInboxService(self.db)
        if request.capture_session_id is not None:
            try:
                session = inbox_service.get_session(request.capture_session_id)
            except Exception as exc:  # noqa: BLE001
                raise DouyinExtensionCaptureError(
                    "capture_session_not_found",
                    "Explicit Capture Inbox session was not found for full modal harvest ingest.",
                    stage="resolve_capture_session",
                ) from exc
            self._validate_explicit_harvest_session(request, session)
            return session
        if request.capture_session_source in {"whole_profile_harvest", "whole_profile_staged_harvest_v2"} and request.run_id:
            if request.capture_session_source == "whole_profile_staged_harvest_v2":
                v2_session = self._find_v2_capture_session_by_run_id(request.run_id)
                if v2_session is not None:
                    return v2_session
            session = self._find_capture_session_by_source_run_id(request.capture_session_source, request.run_id)
            if session is not None:
                return session
        stmt = (
            select(CaptureSession)
            .where(CaptureSession.source_platform == SourcePlatformEnum.DOUYIN)
            .order_by(CaptureSession.created_at.desc())
        )
        capture_session = self.db.scalars(stmt).first()
        if capture_session is None:
            raise DouyinExtensionCaptureError(
                "capture_session_not_found",
                "No Douyin Capture Inbox session is available for full modal harvest ingest.",
                stage="resolve_capture_session",
            )
        return capture_session

    def _find_capture_session_by_source_run_id(self, source: str, run_id: str) -> CaptureSession | None:
        capture_id = f"{source}:{run_id}"
        return self.db.scalar(
            select(CaptureSession).where(
                CaptureSession.source_platform == SourcePlatformEnum.DOUYIN,
                CaptureSession.capture_source == source,
                CaptureSession.capture_id == capture_id,
            )
        )

    def _find_v2_capture_session_by_run_id(self, run_id: str) -> CaptureSession | None:
        return self._find_capture_session_by_source_run_id("whole_profile_staged_harvest_v2", run_id)

    def _validate_explicit_harvest_session(self, request: DouyinExtensionFullModalHarvestRequest, session: CaptureSession) -> None:
        if request.capture_session_source and request.capture_session_source != getattr(session, "capture_source", None):
            raise DouyinExtensionCaptureError(
                "capture_session_not_found",
                "Explicit Capture Inbox session source does not match the full modal harvest payload.",
                stage="resolve_capture_session",
            )
        if request.profile_url and getattr(session, "submitted_profile_url", None) and request.profile_url != session.submitted_profile_url:
            raise DouyinExtensionCaptureError(
                "capture_session_not_found",
                "Explicit Capture Inbox session profile does not match the full modal harvest payload.",
                stage="resolve_capture_session",
            )

    def _build_harvest_plan_summary(self, videos: list[Any], *, harvest_mode: str = "new_and_incomplete") -> dict[str, Any]:
        seen: set[str] = set()
        captured_aweme_ids: list[str] = []
        new_aweme_ids: list[str] = []
        incomplete_aweme_ids: list[str] = []
        complete_aweme_ids: list[str] = []
        skipped_aweme_ids: list[str] = []
        effective_mode = harvest_mode if harvest_mode in {"new_only", "new_and_incomplete", "refresh_all"} else "new_and_incomplete"
        for video in videos:
            aweme_id = str(getattr(video, "aweme_id", None) or getattr(video, "video_id", None) or getattr(video, "id", None) or "").strip()
            if not aweme_id:
                source_url = str(getattr(video, "source_video_url", None) or getattr(video, "url", None) or getattr(video, "share_url", None) or "")
                aweme_id = str(_video_id_from_url(source_url) or "").strip()
            if not aweme_id or aweme_id in seen:
                if aweme_id:
                    skipped_aweme_ids.append(aweme_id)
                continue
            seen.add(aweme_id)
            captured_aweme_ids.append(aweme_id)
            existing = self.db.scalar(
                select(SourceVideo).where(
                    SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                    SourceVideo.source_video_external_id == aweme_id,
                )
            )
            if existing is None:
                new_aweme_ids.append(aweme_id)
            elif isDouyinCaptureItemMetadataComplete(existing):
                complete_aweme_ids.append(aweme_id)
            else:
                incomplete_aweme_ids.append(aweme_id)
        if effective_mode == "refresh_all":
            target_aweme_ids = captured_aweme_ids
        elif effective_mode == "new_only":
            target_aweme_ids = new_aweme_ids
        else:
            target_aweme_ids = new_aweme_ids + incomplete_aweme_ids
        return {
            "harvest_mode": effective_mode,
            "total_found": len(seen),
            "new_count": len(new_aweme_ids),
            "incomplete_count": len(incomplete_aweme_ids),
            "complete_count": len(complete_aweme_ids),
            "skipped_count": len(skipped_aweme_ids),
            "target_count": len(target_aweme_ids),
            "target_aweme_ids": target_aweme_ids,
            "new_aweme_ids": new_aweme_ids,
            "incomplete_aweme_ids": incomplete_aweme_ids,
            "complete_aweme_ids": complete_aweme_ids,
            "skipped_aweme_ids": skipped_aweme_ids,
        }

    def _profile_card_evidence_by_aweme_id(self, videos: list[Any]) -> dict[str, Any]:
        evidence: dict[str, Any] = {}
        for video in videos:
            aweme_id = str(getattr(video, "aweme_id", None) or getattr(video, "video_id", None) or getattr(video, "id", None) or "").strip()
            if not aweme_id:
                continue
            raw_card = video.model_dump(mode="json", exclude_none=True) if hasattr(video, "model_dump") else {}
            evidence[aweme_id] = {
                "aweme_id": aweme_id,
                "source_url": getattr(video, "source_video_url", None) or getattr(video, "url", None) or getattr(video, "share_url", None),
                "title": getattr(video, "title", None),
                "caption": getattr(video, "caption", None),
                "desc": getattr(video, "desc", None),
                "description": getattr(video, "description", None),
                "thumbnail_url": getattr(video, "thumbnail_url", None) or getattr(video, "cover_url", None) or getattr(video, "poster_url", None),
                "cover_url": getattr(video, "cover_url", None),
                "poster_url": getattr(video, "poster_url", None),
                "posted_text": getattr(video, "posted_display", None) or getattr(video, "posted_text", None),
                "posted_text_raw": getattr(video, "posted_text_raw", None) or getattr(video, "posted_text", None),
                "posted_at": getattr(video, "posted_at", None),
                "posted_display": getattr(video, "posted_display", None),
                "posted_parse_confidence": getattr(video, "posted_parse_confidence", None),
                "raw_profile_card": raw_card,
            }
        return evidence

    def _is_finalized_modal_payload(self, payload: Any) -> bool:
        metrics = payload.raw_dom_detail_metrics
        evidence = payload.profile_card_evidence
        if payload.data_integrity_status in {"mismatch", "failed"}:
            return False
        if not str(payload.aweme_id or "").strip():
            return False
        if not (payload.source_url or (evidence and evidence.source_url)):
            return False
        return bool(
            metrics.duration_seconds is not None
            and metrics.duration_seconds > 0
            and metrics.like_count is not None
            and metrics.like_count >= 0
            and metrics.comment_count is not None
            and metrics.comment_count >= 0
            and metrics.favorite_count is not None
            and metrics.favorite_count >= 0
            and metrics.share_count is not None
            and metrics.share_count >= 0
        )

    def _create_finalized_harvest_item(self, session: CaptureSession, payload: Any, *, raw_item_index: int) -> CapturedItem:
        evidence = payload.profile_card_evidence
        source_url = payload.source_url or (evidence.source_url if evidence else None) or f"https://www.douyin.com/video/{payload.aweme_id}"
        evidence_payload = evidence.model_dump(mode="json", exclude_none=True) if evidence else {}
        thumbnail_url = _thumbnail_url_from_payload(evidence_payload) if evidence_payload else None
        caption = (evidence.title or evidence.caption or evidence.desc or evidence.description) if evidence else None
        item = CapturedItem(
            workspace_id=session.workspace_id,
            capture_session_id=session.id,
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.PREVIEW_MISSING,
            raw_item_index=raw_item_index,
            raw_payload_json={"aweme_id": payload.aweme_id, "source_url": source_url, "profile_card_evidence": evidence_payload or None},
            source_profile_external_id=session.normalized_profile_identifier,
            profile_url=session.submitted_profile_url,
            source_video_external_id=payload.aweme_id,
            source_url=source_url,
            share_url=source_url,
            caption=caption,
            thumbnail_url=thumbnail_url,
            preview_url=thumbnail_url,
            preview_ready=bool(thumbnail_url),
            media_ready=False,
            readiness_reasons_json=[],
            dedupe_key=f"douyin:video:{payload.aweme_id}",
            metadata_json={"phase17a_finalized_only": True, "finalized_metadata_source": payload.finalized_metadata_source or "modal_detail_extraction", "profile_card_evidence": evidence_payload or None},
        )
        self.db.add(item)
        self.db.flush()
        if hasattr(session, "items"):
            existing_items = list(getattr(session, "items", []) or [])
            if item not in existing_items:
                try:
                    session.items = [*existing_items, item]
                except Exception:
                    pass
        return item

    def _apply_modal_harvest_to_item(self, item: CapturedItem, payload) -> dict[str, bool]:
        metadata = dict(item.metadata_json or {})
        evidence = payload.profile_card_evidence
        previous_caption = item.caption
        previous_raw_payload = dict(item.raw_payload_json or {})
        previous_duration = item.duration_seconds
        previous_like = metadata.get("like_count")
        previous_comment = metadata.get("comment_count")
        previous_share = metadata.get("share_count")
        previous_favorite = metadata.get("favorite_count")
        previous_posted_text = metadata.get("posted_text")
        previous_thumbnail_url = getattr(item, "thumbnail_url", None)
        previous_dom_detail = metadata.get("raw_dom_detail_metrics")
        previous_estimated_views = metadata.get("estimated_views")

        raw_dom_detail_metrics = payload.raw_dom_detail_metrics.model_dump(mode="json", exclude_none=True)
        raw_evidence_summary = self._merge_dom_detail_evidence_summary(
            existing=metadata.get("raw_evidence_summary") if isinstance(metadata.get("raw_evidence_summary"), dict) else {},
            incoming=payload.raw_evidence_summary.model_dump(mode="json"),
        )
        raw_detail_aweme = payload.raw_detail_aweme
        if hasattr(raw_detail_aweme, "model_dump"):
            raw_detail_aweme = raw_detail_aweme.model_dump(mode="json", exclude_none=True)

        normalized = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=metadata.get("raw_network_aweme") if isinstance(metadata.get("raw_network_aweme"), dict) else None,
                raw_detail_aweme=raw_detail_aweme if isinstance(raw_detail_aweme, dict) else (metadata.get("raw_detail_aweme") if isinstance(metadata.get("raw_detail_aweme"), dict) else None),
                raw_dom_snapshot=metadata.get("raw_dom_snapshot") if isinstance(metadata.get("raw_dom_snapshot"), dict) else None,
                raw_dom_detail_metrics=raw_dom_detail_metrics,
                raw_evidence_summary=raw_evidence_summary,
                existing_posted_at=item.posted_at,
                existing_posted_text=metadata.get("posted_text") if isinstance(metadata.get("posted_text"), str) else None,
                existing_duration_seconds=item.duration_seconds,
                existing_duration_text=metadata.get("duration_text") if isinstance(metadata.get("duration_text"), str) else None,
                existing_view_count=_int_or_none(metadata.get("view_count")),
                existing_like_count=_int_or_none(metadata.get("like_count")),
                existing_comment_count=_int_or_none(metadata.get("comment_count")),
                existing_share_count=_int_or_none(metadata.get("share_count")),
                existing_engagement_rate=_float_or_none(metadata.get("engagement_rate")),
            )
        )
        evidence_posted_text = str(getattr(evidence, "posted_text", "") or "").strip() if evidence is not None else ""
        evidence_posted_text_raw = str(getattr(evidence, "posted_text_raw", "") or "").strip() if evidence is not None else ""
        evidence_posted_at = getattr(evidence, "posted_at", None) if evidence is not None else None
        evidence_posted_display = str(getattr(evidence, "posted_display", "") or "").strip() if evidence is not None else ""
        evidence_payload = evidence.model_dump(mode="json", exclude_none=True) if evidence is not None and hasattr(evidence, "model_dump") else {}
        evidence_thumbnail_url = _thumbnail_url_from_payload(evidence_payload) if evidence_payload else None
        incoming_title = _real_title_from_modal_payload(
            evidence_payload=evidence_payload,
            raw_dom_detail_metrics=raw_dom_detail_metrics,
            aweme_id=str(payload.aweme_id or "").strip() or None,
            source_video_external_id=str(getattr(item, "source_video_external_id", None) or "").strip() or None,
        )
        if incoming_title:
            item.caption = incoming_title
        if evidence_payload:
            raw_payload = dict(item.raw_payload_json or {})
            raw_payload["aweme_id"] = raw_payload.get("aweme_id") or payload.aweme_id
            raw_payload["source_url"] = raw_payload.get("source_url") or payload.source_url or getattr(evidence, "source_url", None)
            raw_payload["profile_card_evidence"] = evidence_payload
            raw_payload["title"] = incoming_title or raw_payload.get("title")
            item.raw_payload_json = {key: value for key, value in raw_payload.items() if value is not None}
        normalized_posted_at = normalized.posted_at or evidence_posted_at
        normalized_posted_display = evidence_posted_display or (normalized_posted_at.strftime("%d/%m/%Y") if hasattr(normalized_posted_at, "strftime") and normalized_posted_at else None)
        normalized_posted_text_raw = evidence_posted_text_raw or evidence_posted_text or (metadata.get("posted_text_raw") if isinstance(metadata.get("posted_text_raw"), str) else None)
        normalized_posted_text = normalized_posted_display or normalized.posted_text or evidence_posted_text or None
        if evidence_thumbnail_url and not getattr(item, "thumbnail_url", None):
            item.thumbnail_url = evidence_thumbnail_url
            item.preview_url = evidence_thumbnail_url
            item.preview_ready = True
        logger.info(
            "full_modal_harvest_normalized",
            extra={
                "item_id": str(item.id),
                "aweme_id": str(item.source_video_external_id).strip() if item.source_video_external_id else None,
                "duration_seconds": normalized.duration_seconds,
                "like_count": normalized.like_count,
                "comment_count": normalized.comment_count,
                "share_count": normalized.share_count,
                "performance_status": normalized.performance_status,
                "processing_fit_status": normalized.processing_fit_status,
                "metadata_status": normalized.metadata_status,
            },
        )

        item.posted_at = normalized_posted_at
        item.duration_seconds = normalized.duration_seconds
        estimated_view_metadata = {}
        payload_estimated_views = self._finite_non_negative_int(payload.estimated_views)
        if payload_estimated_views is not None:
            estimated_view_metadata = {
                "estimated_views": payload_estimated_views,
                "estimated_views_formula": payload.estimated_views_formula,
                "estimated_views_used": payload.estimated_views_used,
                "real_view_count_available": payload.real_view_count_available,
                "real_view_count_data_quality": payload.real_view_count_data_quality,
                "real_view_count_overwritten": payload.real_view_count_overwritten or False,
            }

        metadata.update(
            {
                "raw_dom_detail_metrics": raw_dom_detail_metrics,
                "raw_evidence_summary": raw_evidence_summary,
                "profile_card_evidence": evidence_payload or metadata.get("profile_card_evidence"),
                "title": incoming_title or metadata.get("title"),
                "target_aweme_id": payload.target_aweme_id,
                "modal_aweme_id_before_extract": payload.modal_aweme_id_before_extract,
                "modal_aweme_id_after_extract": payload.modal_aweme_id_after_extract,
                "extracted_aweme_id": payload.extracted_aweme_id,
                "data_integrity_status": payload.data_integrity_status,
                "data_integrity_reason": payload.data_integrity_reason,
                "finalized_metadata_source": payload.finalized_metadata_source,
                "metric_signature": payload.metric_signature,
                "duplicate_signature_warning": payload.duplicate_signature_warning,
                "posted_at": normalized_posted_at.isoformat() if hasattr(normalized_posted_at, "isoformat") and normalized_posted_at else normalized_posted_at,
                "posted_text": normalized_posted_text,
                "posted_text_raw": normalized_posted_text_raw,
                "posted_display": normalized_posted_display,
                "thumbnail_url": getattr(item, "thumbnail_url", None),
                "thumbnail_source": getattr(evidence, "thumbnail_source", None) or ("profile_card" if evidence_thumbnail_url else metadata.get("thumbnail_source")),
                "duration_seconds": normalized.duration_seconds,
                "duration_text": normalized.duration_text,
                "view_count": normalized.view_count,
                "like_count": normalized.like_count,
                "comment_count": normalized.comment_count,
                "share_count": normalized.share_count,
                "favorite_count": _int_or_none(raw_dom_detail_metrics.get("favorite_count")),
                "favorite_count_text": raw_dom_detail_metrics.get("favorite_count_text"),
                "share_count_text": raw_dom_detail_metrics.get("share_count_text"),
                "like_count_text": raw_dom_detail_metrics.get("like_count_text"),
                "comment_count_text": raw_dom_detail_metrics.get("comment_count_text"),
                "engagement_rate": normalized.engagement_rate,
                "posted_source": getattr(evidence, "posted_source", None) or normalized.posted_source,
                "posted_parse_confidence": getattr(evidence, "posted_parse_confidence", None) or raw_dom_detail_metrics.get("posted_parse_confidence") or metadata.get("posted_parse_confidence"),
                "duration_source": normalized.duration_source,
                "view_count_source": normalized.view_count_source,
                "like_count_source": normalized.like_count_source,
                "comment_count_source": normalized.comment_count_source,
                "share_count_source": normalized.share_count_source,
                "engagement_rate_source": normalized.engagement_rate_source,
                "metadata_status": normalized.metadata_status,
                "time_status": normalized.time_status,
                "performance_status": normalized.performance_status,
                "processing_fit_status": normalized.processing_fit_status,
                "metadata_missing_reason": normalized.metadata_missing_reason,
                "time_missing_reason": normalized.time_missing_reason,
                "performance_missing_reason": normalized.performance_missing_reason,
                "processing_fit_missing_reason": normalized.processing_fit_missing_reason,
                "metadata_source_summary": normalized.metadata_source_summary,
                "last_metadata_hydrated_at": datetime.now(UTC).isoformat(),
                **estimated_view_metadata,
            }
        )
        metadata = {key: value for key, value in metadata.items() if value is not None or key in {"raw_dom_detail_metrics", "raw_evidence_summary"}}
        item.metadata_json = metadata
        if item.status not in {CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED, CapturedItemStatus.PROMOTED, CapturedItemStatus.FAILED}:
            item.status = CapturedItemStatus.READY if item.preview_ready else CapturedItemStatus.PREVIEW_MISSING

        metadata_complete = bool(getattr(item, "source_video_external_id", None) and getattr(item, "source_url", None) and item.duration_seconds is not None and metadata.get("like_count") is not None and metadata.get("comment_count") is not None and metadata.get("favorite_count") is not None and metadata.get("share_count") is not None and (item.posted_at is not None or metadata.get("posted_text")) and getattr(item, "thumbnail_url", None))
        if metadata_complete:
            metadata["metadata_status"] = "complete"
            metadata["time_status"] = "captured"
            metadata["performance_status"] = "captured"
            metadata["processing_fit_status"] = "captured"
            item.status = CapturedItemStatus.READY
        elif not getattr(item, "thumbnail_url", None) or not (item.posted_at is not None or metadata.get("posted_text")):
            metadata["metadata_status"] = "partial"
            metadata["metadata_missing_reason"] = "Thumbnail or posted metadata is missing."
            if item.status == CapturedItemStatus.READY:
                item.status = CapturedItemStatus.NEEDS_ENRICHMENT

        updated = any(
            (
                previous_caption != item.caption,
                previous_raw_payload != dict(item.raw_payload_json or {}),
                previous_duration != item.duration_seconds,
                previous_like != metadata.get("like_count"),
                previous_comment != metadata.get("comment_count"),
                previous_share != metadata.get("share_count"),
                previous_favorite != metadata.get("favorite_count"),
                previous_posted_text != metadata.get("posted_text"),
                previous_thumbnail_url != getattr(item, "thumbnail_url", None),
                previous_dom_detail != raw_dom_detail_metrics,
                previous_estimated_views != metadata.get("estimated_views"),
            )
        )
        logger.info(
            "full_modal_harvest_persisted",
            extra={
                "item_id": str(item.id),
                "aweme_id": str(item.source_video_external_id).strip() if item.source_video_external_id else None,
                "updated": updated,
                "duration_seconds": item.duration_seconds,
                "like_count": metadata.get("like_count"),
                "comment_count": metadata.get("comment_count"),
                "share_count": metadata.get("share_count"),
                "favorite_count": metadata.get("favorite_count"),
                "has_dom_detail_metrics": isinstance(metadata.get("raw_dom_detail_metrics"), dict),
                "estimated_views": metadata.get("estimated_views"),
                "estimated_views_formula": metadata.get("estimated_views_formula"),
            },
        )
        return {
            "updated": updated,
            "duration_updated": previous_duration != item.duration_seconds and item.duration_seconds is not None,
            "like_updated": previous_like != metadata.get("like_count") and metadata.get("like_count") is not None,
            "comment_updated": previous_comment != metadata.get("comment_count") and metadata.get("comment_count") is not None,
            "favorite_updated": previous_favorite != metadata.get("favorite_count") and metadata.get("favorite_count") is not None,
            "share_updated": previous_share != metadata.get("share_count") and metadata.get("share_count") is not None,
            "estimated_views_persisted": payload_estimated_views is not None and metadata.get("estimated_views") == payload_estimated_views,
            "title_persisted": incoming_title is not None and item.caption == incoming_title,
        }

    def _finite_non_negative_int(self, value: Any) -> int | None:
        if isinstance(value, bool) or value is None:
            return None
        if isinstance(value, int):
            return value if value >= 0 else None
        if isinstance(value, float) and math.isfinite(value) and value >= 0:
            return int(value)
        return None

    def _merge_dom_detail_evidence_summary(self, *, existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
        merged_sources = sorted({*([value for value in existing.get("evidence_sources", []) if isinstance(value, str)]), *([value for value in incoming.get("evidence_sources", []) if isinstance(value, str)])})
        evidence_collection_version = incoming.get("evidence_collection_version") if isinstance(incoming.get("evidence_collection_version"), str) else existing.get("evidence_collection_version")
        return {
            **existing,
            **incoming,
            "has_network_aweme": bool(existing.get("has_network_aweme")),
            "has_detail_aweme": bool(existing.get("has_detail_aweme")),
            "has_dom_snapshot": bool(existing.get("has_dom_snapshot")),
            "has_dom_detail_metrics": True,
            "network_keys": list(existing.get("network_keys", []))[:40],
            "detail_keys": list(existing.get("detail_keys", []))[:40],
            "dom_detail_metric_keys": list(incoming.get("dom_detail_metric_keys", []))[:40],
            "evidence_sources": merged_sources,
            "evidence_collection_version": evidence_collection_version or "phase6h_full_modal_auto_harvest",
        }

    def _resolve_page_type(
        self,
        *,
        page_type: DouyinExtensionPageType | None,
        page_url: str | None,
        title: str | None,
        body_text: str | None,
        video_link_count: int,
    ) -> DouyinExtensionPageType:
        if page_type in {
            "login_page",
            "challenge_page",
            "home_feed_page",
            "profile_page",
            "profile_feed_page",
            "video_detail_page",
            "unsupported_page",
            "unknown_page",
        }:
            return page_type
        return classify_current_page(page_url=page_url, title=title, body_text=body_text, video_link_count=video_link_count)  # type: ignore[return-value]

    def _resolve_profile_url(self, request: DouyinExtensionDetectPageRequest | DouyinExtensionCaptureRequest, *, detected_page_type: str) -> str | None:
        page = request.page
        explicit = _safe_douyin_profile_url(page.profile_url)
        if explicit is not None:
            return explicit
        from_page = profile_url_from_current_page(page.url) if detected_page_type in {"profile_page", "profile_feed_page"} else None
        if from_page is not None:
            return from_page
        external_id = page.profile_external_id or (request.profile.sec_uid if isinstance(request, DouyinExtensionCaptureRequest) and request.profile else None)
        if external_id:
            return f"https://www.douyin.com/user/{external_id}"
        handle = page.handle or (request.profile.handle if isinstance(request, DouyinExtensionCaptureRequest) and request.profile else None)
        if handle:
            return f"https://www.douyin.com/@{handle.lstrip('@')}"
        if detected_page_type == "video_detail_page" and page.url:
            return _profile_url_from_video_url(page.url)
        return None

    def _to_adapter_payload(self, request: DouyinExtensionCaptureRequest, *, profile_url: str, detected_page_type: str) -> dict:
        profile = request.profile.model_dump(exclude_none=True) if request.profile is not None else {}
        if not profile.get("id") and not profile.get("sec_uid"):
            identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
            profile.setdefault("id", identity.source_profile_external_id)
            profile.setdefault("sec_uid", identity.source_profile_external_id)
        if request.page.display_name and not profile.get("display_name"):
            profile["display_name"] = request.page.display_name
        if request.page.handle and not profile.get("handle"):
            profile["handle"] = request.page.handle.lstrip("@")

        videos = []
        for item in request.videos:
            video = item.model_dump(exclude_none=True)
            statistics = video.get("statistics") if isinstance(video.get("statistics"), dict) else {}
            stats = video.get("stats") if isinstance(video.get("stats"), dict) else {}
            merged_stats = {**stats, **statistics}
            if merged_stats:
                video["statistics"] = merged_stats
            video.pop("stats", None)
            videos.append(video)

        diagnostics = self._safe_diagnostics(request.diagnostics)
        metadata = {
            "source": "douyin_extension_capture",
            "capture_model": "operator_real_browser_current_tab",
            "capture_id": request.capture_id,
            "captured_at": request.captured_at.isoformat() if request.captured_at else None,
            "schema_version": request.schema_version,
            "detected_page_type": detected_page_type,
            "extension_page_type": detected_page_type,
            "fetch_execution_path": EXTENSION_FETCH_PATH,
            "final_execution_path_used": EXTENSION_FETCH_PATH,
            "primary_execution_path": EXTENSION_FETCH_PATH,
            "strategy_policy": EXTENSION_STRATEGY_POLICY,
            "http_fallback_attempted": False,
            "browser_profile_available": True,
            "parse_strategy": "extension_visible_dom_v1",
            "raw_video_item_count": len(videos),
            "video_candidate_count": len(videos),
            "profile_payload_present": bool(profile),
            "current_page_url": request.page.url,
            "current_page_title": request.page.title,
            "current_page_video_link_count": request.page.video_link_count,
            "extension_diagnostics": diagnostics,
            "response_classification": {
                "result": "warning" if len(videos) == 0 else "ok",
                "code": "true_zero_videos" if len(videos) == 0 else "response.classified.ok",
                "message": "Extension capture returned zero visible videos." if len(videos) == 0 else "Extension capture returned visible videos.",
            },
        }
        return {"profile": profile, "videos": videos, "metadata": metadata}

    def _safe_diagnostics(self, diagnostics: dict[str, Any]) -> dict[str, Any]:
        safe: dict[str, Any] = {}
        for key, value in diagnostics.items():
            lowered = key.lower()
            if any(marker in lowered for marker in SECRET_KEY_MARKERS):
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                safe[key] = value
        return safe

    def _reject_secret_payload(self, payload: Any, *, diagnostics_id: str, stage: str) -> None:
        secret_path = _find_secret_path(payload)
        if secret_path is not None:
            raise DouyinExtensionCaptureError(
                "extension_payload_contains_secret_field",
                f"Extension payload contains a disallowed secret-like field: {secret_path}.",
                stage=stage,
                diagnostics_id=diagnostics_id,
            )


def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _real_title_from_modal_payload(
    *,
    evidence_payload: dict[str, Any],
    raw_dom_detail_metrics: dict[str, Any],
    aweme_id: str | None,
    source_video_external_id: str | None,
) -> str | None:
    blocked = {value for value in (aweme_id, source_video_external_id) if value}
    for value in (
        evidence_payload.get("title"),
        evidence_payload.get("caption"),
        evidence_payload.get("desc"),
        evidence_payload.get("description"),
        raw_dom_detail_metrics.get("title"),
    ):
        title = _string_or_none(value)
        if title and title not in blocked:
            return title
    return None


def _status_counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value or "unknown")
        counts[key] = counts.get(key, 0) + 1
    return counts


def extension_page_operator_guidance(page_type: str, *, supported_capture: bool) -> tuple[str, str, str]:
    if supported_capture:
        return (
            "capture_current_page",
            "Capture current page",
            "This Douyin page can be imported from the extension using your real browser session.",
        )
    if page_type == "login_page":
        return ("complete_login", "Complete login", "Complete login in your real browser, then navigate to the target Douyin page and detect again.")
    if page_type == "challenge_page":
        return ("solve_challenge", "Solve challenge", "Solve the visible Douyin challenge manually in your browser, then capture again from the target page.")
    if page_type == "home_feed_page":
        return ("scroll_or_open_profile", "Scroll or open profile", "The home feed can be captured when visible video cards are present, but a creator profile page is usually better.")
    if page_type == "video_detail_page":
        return ("capture_current_video", "Capture current video", "This video detail page can be captured if profile ownership and a video id are visible.")
    if page_type == "unsupported_page":
        return ("open_douyin", "Open Douyin", "The current page is outside Douyin. Open a supported Douyin page in your real browser.")
    return ("inspect_current_page", "Inspect current page", "The current page is not recognized as a capturable Douyin page.")


def _safe_douyin_profile_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    if "douyin.com" not in parsed.netloc.lower() and "iesdouyin.com" not in parsed.netloc.lower():
        return None
    if re.search(r"(^|/)user/[^/?#]+", parsed.path.strip("/")) or parsed.path.strip("/").startswith("@"):
        return value
    return None


def _profile_url_from_video_url(value: str) -> str | None:
    parsed = urlparse(value)
    query_profile = None
    if parsed.query:
        for part in parsed.query.split("&"):
            if part.startswith("sec_uid="):
                query_profile = part.split("=", 1)[1]
                break
    if query_profile:
        return f"https://www.douyin.com/user/{query_profile}"
    return None


def _find_secret_path(value: Any, *, path: str = "payload") -> str | None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            if any(marker in lowered for marker in SECRET_KEY_MARKERS):
                return f"{path}.{key}"
            found = _find_secret_path(child, path=f"{path}.{key}")
            if found is not None:
                return found
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found = _find_secret_path(child, path=f"{path}[{index}]")
            if found is not None:
                return found
    return None


def isDouyinCaptureItemMetadataComplete(item: Any) -> bool:
    metadata = getattr(item, "metadata_json", None) if not isinstance(item, dict) else item.get("metadata_json")
    metadata = metadata if isinstance(metadata, dict) else {}

    def first_value(name: str) -> Any:
        if isinstance(item, dict) and item.get(name) is not None:
            return item.get(name)
        value = getattr(item, name, None)
        return value if value is not None else metadata.get(name)

    if not str(first_value("source_video_external_id") or "").strip():
        return False
    if first_value("duration_seconds") is None:
        return False
    for field in ("like_count", "comment_count", "favorite_count", "share_count"):
        if _int_or_none(metadata.get(field)) is None:
            return False
    if first_value("posted_at") is None and not str(metadata.get("posted_text") or "").strip():
        return False
    return True
