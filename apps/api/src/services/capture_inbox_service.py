from __future__ import annotations

from dataclasses import dataclass
import json
import re
from datetime import UTC, datetime
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import Select, String, Text, and_, case, cast, distinct, func, inspect, or_, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.errors import SourceAdapterError
from src.db.bootstrap import ensure_default_workspace
from src.enums import CandidateStatus, CaptureSessionStatus, CapturedItemStatus, CrawlSessionStatus, IntakeEvaluationStatus, SourcePlatformEnum
from src.models.capture_inbox import CapturedItem, CaptureSession
from src.models.ingestion import SourceVideo
from src.models.review import VideoCandidate
from src.schemas.capture_inbox import CaptureInboxAdvancedFilterRequest, CaptureInboxStudioStatus, CaptureSessionCountsResponse
from src.schemas.douyin_extension import DouyinExtensionCaptureRequest
from src.services.candidate_filter import apply_candidate_filter
from src.services.candidate_service import CandidateEvaluationService
from src.services.candidate_types import CandidateSourceRecord, FilterConfig, MetricSnapshotInput
from src.services.filter_presets import resolve_filter_config
from src.services.capture_metadata_normalizer import CaptureMetadataNormalizeInput, CaptureMetadataNormalizer
from src.services.source_ingest_service import SourceIngestError, SourceIngestService

logger = logging.getLogger(__name__)

CAPTURE_SOURCE_EXTENSION = "douyin_extension_current_tab"
CAPTURE_INBOX_CRAWL_MODE = "extension_capture_inbox_promotion"
CAPTURE_INBOX_ROUTE = "/ops/extensions/douyin/capture-inbox"
_CAPTURED_ITEM_LIST_ORDER = (CapturedItem.created_at.desc(), CapturedItem.id.desc())


def _counts_from_status_map(status_counts: dict[CapturedItemStatus, int]) -> CaptureSessionCountsResponse:
    ready = status_counts.get(CapturedItemStatus.READY, 0)
    dup = status_counts.get(CapturedItemStatus.DUPLICATE, 0)
    fail = status_counts.get(CapturedItemStatus.FAILED, 0)
    skipped = status_counts.get(CapturedItemStatus.EXCLUDED, 0)
    captured = sum(status_counts.values())
    return CaptureSessionCountsResponse(
        captured=captured,
        ready=ready,
        needs_action=max(0, captured - ready - dup - fail - skipped),
        dup=dup,
        fail=fail,
    )


@dataclass(frozen=True)
class CaptureInboxItemFailureSummary:
    stage: str
    item_index: int | None
    code: str
    message: str


@dataclass(frozen=True)
class CaptureInboxStageResult:
    session: CaptureSession
    items: list[CapturedItem]
    failure_summaries: list[CaptureInboxItemFailureSummary]
    warning_codes: list[str]
    stage: str


@dataclass(frozen=True)
class CaptureInboxPromotionSkip:
    item_id: UUID
    reason: str


@dataclass(frozen=True)
class CaptureInboxPromotionResult:
    session: CaptureSession
    items: list[CapturedItem]
    promoted_item_count: int
    candidate_created_count: int
    candidate_updated_count: int
    skipped: list[CaptureInboxPromotionSkip]
    failed: list[CaptureInboxPromotionSkip]


@dataclass(frozen=True)
class CaptureInboxDeleteResult:
    session: CaptureSession
    deleted_item_ids: list[UUID]
    skipped_promoted_item_ids: list[UUID]


TARGET_DEBUG_AWEME_IDS = {"7628281732369796388", "7631223404342857006", "7628596519502892307"}
TARGET_DEBUG_FIELDS = (
    "posted_at",
    "posted_text",
    "duration_seconds",
    "duration_text",
    "view_count",
    "like_count",
    "comment_count",
    "share_count",
)


class CaptureInboxError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class CaptureInboxRuntimeError(CaptureInboxError):
    def __init__(self, code: str, message: str, *, stage: str, diagnostics_id: str | None = None):
        super().__init__(code, message)
        self.stage = stage
        self.diagnostics_id = diagnostics_id


_REQUIRED_CAPTURE_INBOX_COLUMNS: dict[str, set[str]] = {
    "capture_sessions": {
        "id",
        "workspace_id",
        "capture_id",
        "source_platform",
        "capture_source",
        "status",
        "detected_page_type",
        "page_url",
        "page_title",
        "submitted_profile_url",
        "normalized_profile_identifier",
        "visible_item_count",
        "captured_item_count",
        "normalized_item_count",
        "duplicate_item_count",
        "ready_item_count",
        "skipped_item_count",
        "promoted_item_count",
        "candidate_created_count",
        "failed_item_count",
        "started_at",
        "finished_at",
        "diagnostics_json",
        "metadata_json",
        "raw_summary_json",
        "result_summary_json",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
    },
    "captured_items": {
        "id",
        "workspace_id",
        "capture_session_id",
        "source_platform",
        "status",
        "raw_item_index",
        "raw_payload_json",
        "source_profile_external_id",
        "profile_url",
        "source_video_external_id",
        "source_url",
        "share_url",
        "caption",
        "duration_seconds",
        "posted_at",
        "thumbnail_url",
        "preview_url",
        "preview_ready",
        "media_ready",
        "readiness_reasons_json",
        "dedupe_key",
        "duplicate_of_item_id",
        "existing_source_video_id",
        "promoted_source_video_id",
        "promoted_video_candidate_id",
        "promoted_crawl_session_id",
        "enrichment_json",
        "metadata_json",
        "excluded_reason",
        "intake_evaluation_status",
        "matches_intake",
        "intake_failed_rules_json",
        "intake_missing_requirements_json",
        "intake_filter_version",
        "intake_preset_name",
        "last_intake_evaluated_at",
        "intake_evaluation_error",
        "error_code",
        "error_message",
        "created_at",
        "updated_at",
    },
}


class CaptureInboxService:
    def __init__(self, db: Session):
        self.db = db

    def stage_extension_capture(
        self,
        request: DouyinExtensionCaptureRequest,
        *,
        diagnostics_id: str,
        detected_page_type: str,
        profile_url: str,
        safe_diagnostics: dict[str, Any],
    ) -> CaptureInboxStageResult:
        self.validate_runtime_schema(diagnostics_id=diagnostics_id)
        workspace = ensure_default_workspace(self.db) if request.workspace_id is None else None
        workspace_id = request.workspace_id or workspace.id
        now = datetime.now(UTC)
        identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
        session_context = _capture_context_dict(request.capture_context)
        session_context = {
            **session_context,
            "capture_id": session_context.get("capture_id") or request.capture_id,
            "workspace_id": str(workspace_id),
            "page_url": session_context.get("page_url") or request.page.url,
            "page_url_normalized": session_context.get("page_url_normalized") or _normalize_context_url(request.page.url),
            "profile_url": session_context.get("profile_url") or profile_url,
            "profile_external_id": session_context.get("profile_external_id") or identity.source_profile_external_id,
            "captured_at": session_context.get("captured_at") or (request.captured_at.isoformat() if request.captured_at else None),
        }
        if request.profile is not None and request.profile.follower_count is not None:
            session_context["follower_count"] = request.profile.follower_count
        session_context = {key: value for key, value in session_context.items() if value is not None}
        session = CaptureSession(
            workspace_id=workspace_id,
            capture_id=request.capture_id,
            source_platform=SourcePlatformEnum.DOUYIN,
            capture_source=CAPTURE_SOURCE_EXTENSION,
            status=CaptureSessionStatus.RECEIVED,
            detected_page_type=detected_page_type,
            page_url=request.page.url,
            page_title=request.page.title,
            submitted_profile_url=profile_url,
            normalized_profile_identifier=identity.source_profile_external_id,
            visible_item_count=request.page.video_link_count or len(request.videos),
            started_at=now,
            diagnostics_json=safe_diagnostics,
            metadata_json={
                "diagnostics_id": diagnostics_id,
                "schema_version": request.schema_version,
                "captured_at": request.captured_at.isoformat() if request.captured_at else None,
                "capture_model": "operator_real_browser_current_tab",
                "review_boundary": "capture_inbox_before_review_board",
                "stage": "capture_session_created",
                "capture_context": session_context,
            },
            raw_summary_json={
                "extension_video_count": len(request.videos),
                "page_video_link_count": request.page.video_link_count,
                "profile_payload_present": request.profile is not None,
                "thumbnail_payload_count": sum(1 for video in request.videos if video.thumbnail_url or video.cover_url or video.poster_url or video.url_list),
                "duration_payload_count": sum(1 for video in request.videos if video.duration_seconds is not None or video.duration_text),
                "posted_payload_count": sum(1 for video in request.videos if video.posted_at is not None or video.posted_text),
                "metric_payload_count": sum(1 for video in request.videos if video.view_count is not None or video.like_count is not None or video.comment_count is not None),
                "preview_ready_payload_count": sum(1 for video in request.videos if video.preview_status == "ready"),
                "media_source_link_payload_count": sum(1 for video in request.videos if video.media_status == "source_link_captured"),
                "thumbnail_candidate_total_count": sum(len(video.url_list or []) for video in request.videos),
            },
        )
        try:
            self.db.add(session)
            self.db.flush()
            self.db.commit()
            self.db.refresh(session)
            session.status = CaptureSessionStatus.ENRICHING
            self.db.commit()
            self.db.refresh(session)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise _runtime_error_from_exception(exc, stage="capture_session_persist", diagnostics_id=diagnostics_id) from exc

        seen: dict[str, CapturedItem] = {}
        items: list[CapturedItem] = []
        failure_summaries: list[CaptureInboxItemFailureSummary] = []
        for index, payload in enumerate(request.videos):
            raw_item: dict[str, Any]
            try:
                raw_item = payload.model_dump(mode="json", exclude_none=True)
                mismatch_codes = _context_mismatch_codes(session_context, raw_item, workspace_id=workspace_id)
                if mismatch_codes:
                    failure = _failure_summary(
                        stage="context_isolation_rejected",
                        item_index=index,
                        code="context_mismatch",
                        message=f"Captured item rejected because it does not match the active capture context: {', '.join(mismatch_codes)}.",
                    )
                    failure_summaries.append(failure)
                    logger.warning(
                        "capture_inbox_context_mismatch_rejected",
                        extra={
                            "capture_session_id": str(session.id),
                            "capture_id": session.capture_id,
                            "workspace_id": str(workspace_id),
                            "raw_item_index": index,
                            "context_mismatch_codes": mismatch_codes,
                        },
                    )
                    continue
                item = self._build_item(
                    session=session,
                    request=request,
                    raw_item=raw_item,
                    raw_item_index=index,
                    profile_url=profile_url,
                    profile_external_id=identity.source_profile_external_id,
                )
                self._enrich_item(item, seen=seen)
            except (ValueError, TypeError, OverflowError, OSError) as exc:
                raw_item = payload.model_dump(mode="json", exclude_none=True)
                failure = _failure_summary(
                    stage="item_normalization_partial_failure",
                    item_index=index,
                    code="item_normalization_failed",
                    message=str(exc) or "Captured item could not be normalized.",
                )
                failure_summaries.append(failure)
                item = self._failed_item(
                    session=session,
                    request=request,
                    raw_item=raw_item,
                    raw_item_index=index,
                    profile_url=profile_url,
                    profile_external_id=identity.source_profile_external_id,
                    failure=failure,
                )

            if item.status == CapturedItemStatus.FAILED and item.error_code and not any(
                failure.item_index == index and failure.code == item.error_code for failure in failure_summaries
            ):
                failure_summaries.append(
                    _failure_summary(
                        stage="item_normalization_partial_failure",
                        item_index=index,
                        code=item.error_code,
                        message=item.error_message or "Captured item failed normalization.",
                    )
                )

            try:
                self.db.add(item)
                self.db.flush()
            except Exception as exc:  # noqa: BLE001 - persist failures are recorded as item/session diagnostics when possible.
                self.db.rollback()
                try:
                    session = self.get_session(session.id)
                except SQLAlchemyError as reload_exc:
                    raise _runtime_error_from_exception(reload_exc, stage="captured_item_persist", diagnostics_id=diagnostics_id) from reload_exc
                seen = {
                    existing.dedupe_key: existing
                    for existing in session.items
                    if existing.dedupe_key and existing.status not in {CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED, CapturedItemStatus.FAILED}
                }
                runtime_failure = _runtime_error_from_exception(exc, stage="captured_item_persist", diagnostics_id=diagnostics_id)
                failure = _failure_summary(
                    stage="item_persist_partial_failure",
                    item_index=index,
                    code=runtime_failure.code if runtime_failure.code in {"schema_missing", "migration_mismatch"} else "captured_item_persist_failed",
                    message=runtime_failure.message,
                )
                failure_summaries.append(failure)
                item = self._failed_item(
                    session=session,
                    request=request,
                    raw_item=raw_item,
                    raw_item_index=index,
                    profile_url=profile_url,
                    profile_external_id=identity.source_profile_external_id,
                    failure=failure,
                )
                try:
                    self.db.add(item)
                    self.db.flush()
                except Exception as retry_exc:  # noqa: BLE001 - session remains more important than one failed item placeholder.
                    self.db.rollback()
                    try:
                        session = self.get_session(session.id)
                    except SQLAlchemyError as reload_exc:
                        raise _runtime_error_from_exception(reload_exc, stage="captured_item_persist", diagnostics_id=diagnostics_id) from reload_exc
                    seen = {
                        existing.dedupe_key: existing
                        for existing in session.items
                        if existing.dedupe_key and existing.status not in {CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED, CapturedItemStatus.FAILED}
                    }
                    retry_failure = _runtime_error_from_exception(retry_exc, stage="captured_item_persist", diagnostics_id=diagnostics_id)
                    failure_summaries.append(
                        _failure_summary(
                            stage="item_persist_partial_failure",
                            item_index=index,
                            code=retry_failure.code if retry_failure.code in {"schema_missing", "migration_mismatch"} else "captured_item_persist_failed",
                            message=retry_failure.message,
                        )
                    )
                    continue
            if item.dedupe_key and item.status != CapturedItemStatus.DUPLICATE:
                seen[item.dedupe_key] = item
            items.append(item)

        self._evaluate_items_against_intake(items, session=session)
        suspicious_duplicate_payload_mapping_count = _suspicious_duplicate_payload_mapping_count(items)
        try:
            self._reconcile_session(session)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise _runtime_error_from_exception(exc, stage="capture_session_reconcile", diagnostics_id=diagnostics_id) from exc
        warning_codes = _warning_codes_for_stage(session, failure_summaries, suspicious_duplicate_payload_mapping_count=suspicious_duplicate_payload_mapping_count)
        stage = "item_normalization_partial_failure" if failure_summaries else "capture_session_staged"
        thumbnail_item_count = sum(1 for item in items if item.thumbnail_url)
        duration_item_count = sum(1 for item in items if item.duration_seconds is not None or (item.metadata_json or {}).get("duration_text"))
        posted_item_count = sum(1 for item in items if item.posted_at is not None or (item.metadata_json or {}).get("posted_text"))
        metric_item_count = sum(1 for item in items if any((item.metadata_json or {}).get(key) is not None for key in ("view_count", "like_count", "comment_count")))
        preview_status_counts = _status_counts((item.metadata_json or {}).get("preview_status") for item in items)
        media_status_counts = _status_counts((item.metadata_json or {}).get("media_status") for item in items)
        session.result_summary_json = {
            **(session.result_summary_json or {}),
            "stage": stage,
            "warning_codes": warning_codes,
            "failure_summaries": [failure.__dict__ for failure in failure_summaries],
            "thumbnail_item_count": thumbnail_item_count,
            "duration_item_count": duration_item_count,
            "posted_item_count": posted_item_count,
            "metric_item_count": metric_item_count,
            "preview_status_counts": preview_status_counts,
            "media_status_counts": media_status_counts,
            "suspicious_duplicate_payload_mapping_count": suspicious_duplicate_payload_mapping_count,
            "context_mismatch_rejected_count": sum(1 for failure in failure_summaries if failure.stage == "context_isolation_rejected"),
        }
        session.metadata_json = {**(session.metadata_json or {}), "stage": stage, "capture_context": session_context}
        logger.info(
            "douyin_capture_session_staged",
            extra={
                "capture_session_id": str(session.id),
                "capture_id": session.capture_id,
                "captured_item_count": session.captured_item_count,
                "ready_item_count": session.ready_item_count,
                "duplicate_item_count": session.duplicate_item_count,
                "failed_item_count": session.failed_item_count,
                "stage": stage,
                "warning_codes": warning_codes,
                "thumbnail_item_count": thumbnail_item_count,
                "duration_item_count": duration_item_count,
                "posted_item_count": posted_item_count,
                "metric_item_count": metric_item_count,
                "preview_status_counts": preview_status_counts,
                "media_status_counts": media_status_counts,
                "suspicious_duplicate_payload_mapping_count": suspicious_duplicate_payload_mapping_count,
            },
        )
        try:
            self.db.commit()
            self.db.refresh(session)
        except SQLAlchemyError as exc:
            self.db.rollback()
            raise _runtime_error_from_exception(exc, stage="capture_session_reconcile", diagnostics_id=diagnostics_id) from exc
        return CaptureInboxStageResult(session=session, items=items, failure_summaries=failure_summaries, warning_codes=warning_codes, stage=stage)

    def validate_runtime_schema(self, *, diagnostics_id: str | None = None) -> None:
        try:
            inspector = inspect(self.db.get_bind())
            table_names = set(inspector.get_table_names())
            missing_tables = sorted(table for table in _REQUIRED_CAPTURE_INBOX_COLUMNS if table not in table_names)
            if missing_tables:
                raise CaptureInboxRuntimeError(
                    "schema_missing",
                    "Capture Inbox database schema is missing required table(s): "
                    f"{', '.join(missing_tables)}. Apply migrations and restart the backend on the extension API port.",
                    stage="capture_inbox_schema_readiness",
                    diagnostics_id=diagnostics_id,
                )
            missing_columns: dict[str, list[str]] = {}
            for table_name, required_columns in _REQUIRED_CAPTURE_INBOX_COLUMNS.items():
                actual_columns = {column["name"] for column in inspector.get_columns(table_name)}
                table_missing_columns = sorted(required_columns - actual_columns)
                if table_missing_columns:
                    missing_columns[table_name] = table_missing_columns
            if missing_columns:
                summary = "; ".join(f"{table}: {', '.join(columns)}" for table, columns in missing_columns.items())
                raise CaptureInboxRuntimeError(
                    "migration_mismatch",
                    "Capture Inbox database schema is behind the backend model. Missing column(s): "
                    f"{summary}. Apply the latest migrations and restart the backend.",
                    stage="capture_inbox_schema_readiness",
                    diagnostics_id=diagnostics_id,
                )
        except CaptureInboxRuntimeError:
            raise
        except SQLAlchemyError as exc:
            raise _runtime_error_from_exception(exc, stage="capture_inbox_schema_readiness", diagnostics_id=diagnostics_id) from exc

    def list_sessions(self, *, status: CaptureSessionStatus | None = None, limit: int = 50, offset: int = 0) -> tuple[list[CaptureSession], int]:
        stmt = (
            select(CaptureSession)
            .options(selectinload(CaptureSession.items))
            .order_by(CaptureSession.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        count_stmt = select(func.count()).select_from(CaptureSession)
        if status is not None:
            stmt = stmt.where(CaptureSession.status == status)
            count_stmt = count_stmt.where(CaptureSession.status == status)
        sessions = list(self.db.scalars(stmt))
        for session in sessions:
            self._apply_session_counts(session, list(getattr(session, "items", []) or []), persist_summary=False)
        return sessions, int(self.db.scalar(count_stmt) or 0)

    def get_session(self, capture_session_id: UUID) -> CaptureSession:
        session = self.db.scalar(
            select(CaptureSession)
            .options(selectinload(CaptureSession.items))
            .where(CaptureSession.id == capture_session_id)
        )
        if session is None:
            raise CaptureInboxError("capture_session_not_found", "Capture session was not found.")
        self._apply_session_counts(session, list(getattr(session, "items", []) or []), persist_summary=False)
        return session

    def delete_session(self, capture_session_id: UUID) -> None:
        session = self.get_session(capture_session_id)
        item_count = len(session.items)
        logger.info(
            "douyin_capture_session_delete_requested",
            extra={
                "capture_session_id": str(session.id),
                "capture_id": session.capture_id,
                "captured_item_count": item_count,
            },
        )
        self.db.delete(session)
        self.db.commit()
        logger.info(
            "douyin_capture_session_deleted",
            extra={
                "capture_session_id": str(capture_session_id),
                "captured_item_count": item_count,
            },
        )

    def list_items(
        self,
        *,
        capture_session_id: UUID | None = None,
        profile_url: str | None = None,
        status: CapturedItemStatus | None = None,
        studio_status: CaptureInboxStudioStatus | None = None,
        search: str | None = None,
        advanced_filter: CaptureInboxAdvancedFilterRequest | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[CapturedItem], int]:
        if capture_session_id is None and profile_url is None:
            raise CaptureInboxError("capture_session_id_required", "Capture Inbox items must be queried for an explicit capture session or profile URL.")
        has_client_filters = bool((search or "").strip()) or advanced_filter is not None
        if profile_url is not None:
            try:
                identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
            except SourceAdapterError as exc:
                raise CaptureInboxError("invalid_profile_url", str(exc)) from exc
            profile_identifier = identity.source_profile_external_id
            base_filters = [
                CapturedItem.source_platform == SourcePlatformEnum.DOUYIN,
                or_(
                    CapturedItem.source_profile_external_id == profile_identifier,
                    CaptureSession.normalized_profile_identifier == profile_identifier,
                ),
            ]
            if status is not None:
                base_filters.append(CapturedItem.status == status)
            if studio_status is not None and studio_status != "all":
                base_filters.append(self._studio_status_clause(studio_status))
            if has_client_filters:
                stmt = (
                    select(CapturedItem)
                    .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
                    .where(*base_filters)
                    .order_by(*_CAPTURED_ITEM_LIST_ORDER)
                )
                scoped_items = list(self.db.scalars(stmt))
                filtered_items = self._filter_items(scoped_items, search=search, advanced_filter=advanced_filter)
                total_count = len(filtered_items)
                return filtered_items[offset : offset + limit], total_count
            total_count = int(
                self.db.scalar(
                    select(func.count())
                    .select_from(CapturedItem)
                    .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
                    .where(*base_filters)
                )
                or 0
            )
            items_stmt = (
                select(CapturedItem)
                .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
                .where(*base_filters)
                .order_by(*_CAPTURED_ITEM_LIST_ORDER)
                .offset(offset)
                .limit(limit)
            )
            return list(self.db.scalars(items_stmt)), total_count
        base_filters = [CapturedItem.capture_session_id == capture_session_id]
        if status is not None:
            base_filters.append(CapturedItem.status == status)
        if studio_status is not None and studio_status != "all":
            base_filters.append(self._studio_status_clause(studio_status))
        if has_client_filters:
            stmt = select(CapturedItem).where(*base_filters).order_by(*_CAPTURED_ITEM_LIST_ORDER)
            scoped_items = list(self.db.scalars(stmt))
            filtered_items = self._filter_items(scoped_items, search=search, advanced_filter=advanced_filter)
            total_count = len(filtered_items)
            return filtered_items[offset : offset + limit], total_count
        total_count = int(self.db.scalar(select(func.count()).select_from(CapturedItem).where(*base_filters)) or 0)
        items_stmt = (
            select(CapturedItem)
            .where(*base_filters)
            .order_by(*_CAPTURED_ITEM_LIST_ORDER)
            .offset(offset)
            .limit(limit)
        )
        return list(self.db.scalars(items_stmt)), total_count

    @staticmethod
    def _studio_status_clause(studio_status: CaptureInboxStudioStatus):
        ready_clause = and_(
            CapturedItem.status.in_((CapturedItemStatus.READY, CapturedItemStatus.ENRICHED)),
            CapturedItem.matches_intake.is_(True),
        )
        promoted_clause = CapturedItem.status == CapturedItemStatus.PROMOTED
        duplicate_clause = CapturedItem.status == CapturedItemStatus.DUPLICATE
        failed_clause = and_(
            CapturedItem.status.notin_(
                (CapturedItemStatus.PROMOTED, CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED)
            ),
            or_(
                CapturedItem.status == CapturedItemStatus.FAILED,
                CapturedItem.intake_evaluation_status.in_(
                    (IntakeEvaluationStatus.FILTERED_OUT, IntakeEvaluationStatus.EVALUATION_ERROR)
                ),
                CapturedItem.matches_intake.is_(False),
            ),
        )
        needs_action_clause = and_(
            CapturedItem.status.notin_(
                (CapturedItemStatus.PROMOTED, CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED)
            ),
            ~ready_clause,
            ~failed_clause,
        )
        clauses = {
            "all": true(),
            "ready": ready_clause,
            "promoted": promoted_clause,
            "duplicate": duplicate_clause,
            "needs_action": needs_action_clause,
            "failed": failed_clause,
        }
        return clauses[studio_status]

    def count_items_by_studio_status(
        self,
        *,
        capture_session_id: UUID | None = None,
        profile_url: str | None = None,
    ) -> dict[str, int]:
        if capture_session_id is None and profile_url is None:
            raise CaptureInboxError(
                "capture_session_id_required",
                "Capture Inbox status counts require an explicit capture session or profile URL.",
            )

        status_keys: tuple[CaptureInboxStudioStatus, ...] = (
            "ready",
            "promoted",
            "duplicate",
            "needs_action",
            "failed",
        )
        stmt = select(
            func.count().label("all"),
            *[
                func.sum(case((self._studio_status_clause(status_key), 1), else_=0)).label(status_key)
                for status_key in status_keys
            ],
        ).select_from(CapturedItem)

        if profile_url is not None:
            try:
                identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
            except SourceAdapterError as exc:
                raise CaptureInboxError("invalid_profile_url", str(exc)) from exc
            stmt = stmt.join(
                CaptureSession,
                CapturedItem.capture_session_id == CaptureSession.id,
            ).where(
                CapturedItem.source_platform == SourcePlatformEnum.DOUYIN,
                or_(
                    CapturedItem.source_profile_external_id == identity.source_profile_external_id,
                    CaptureSession.normalized_profile_identifier == identity.source_profile_external_id,
                ),
            )
        else:
            stmt = stmt.where(CapturedItem.capture_session_id == capture_session_id)

        row = self.db.execute(stmt).one()._mapping
        return {
            "all": int(row["all"] or 0),
            **{status_key: int(row[status_key] or 0) for status_key in status_keys},
        }

    def _profile_unique_video_count(self, base_filters: list) -> int:
        distinct_aweme_count = int(
            self.db.scalar(
                select(func.count(distinct(CapturedItem.source_video_external_id)))
                .select_from(CapturedItem)
                .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
                .where(*base_filters)
                .where(CapturedItem.source_video_external_id.isnot(None))
            )
            or 0
        )
        rows_without_aweme_count = int(
            self.db.scalar(
                select(func.count())
                .select_from(CapturedItem)
                .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
                .where(*base_filters)
                .where(CapturedItem.source_video_external_id.is_(None))
            )
            or 0
        )
        return distinct_aweme_count + rows_without_aweme_count

    def list_profile_items(
        self,
        *,
        profile_url: str,
        limit: int = 500,
        offset: int = 0,
    ) -> tuple[str, str, list[CapturedItem], int, int]:
        try:
            identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
        except SourceAdapterError as exc:
            raise CaptureInboxError("invalid_profile_url", str(exc)) from exc
        profile_identifier = identity.source_profile_external_id
        normalized_profile_url = _normalize_context_url(identity.canonical_url) or identity.canonical_url
        base_filters = [
            CapturedItem.source_platform == SourcePlatformEnum.DOUYIN,
            or_(
                CapturedItem.source_profile_external_id == profile_identifier,
                CaptureSession.normalized_profile_identifier == profile_identifier,
            ),
        ]
        count_stmt = (
            select(func.count())
            .select_from(CapturedItem)
            .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
            .where(*base_filters)
        )
        total_count = int(self.db.scalar(count_stmt) or 0)
        unique_video_count = self._profile_unique_video_count(base_filters)
        items_stmt = (
            select(CapturedItem)
            .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
            .where(*base_filters)
            .order_by(*_CAPTURED_ITEM_LIST_ORDER)
            .offset(offset)
            .limit(limit)
        )
        items = list(self.db.scalars(items_stmt))
        return profile_identifier, normalized_profile_url, items, total_count, unique_video_count

    def get_profile_summary(self, *, profile_url: str) -> tuple[str, str, CaptureSessionCountsResponse, int, int]:
        try:
            identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
        except SourceAdapterError as exc:
            raise CaptureInboxError("invalid_profile_url", str(exc)) from exc
        profile_identifier = identity.source_profile_external_id
        normalized_profile_url = _normalize_context_url(identity.canonical_url) or identity.canonical_url
        base_filters = [
            CapturedItem.source_platform == SourcePlatformEnum.DOUYIN,
            or_(
                CapturedItem.source_profile_external_id == profile_identifier,
                CaptureSession.normalized_profile_identifier == profile_identifier,
            ),
        ]

        stmt = (
            select(CapturedItem.status, func.count())
            .join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id)
            .where(*base_filters)
            .group_by(CapturedItem.status)
        )
        status_counts: dict[CapturedItemStatus, int] = {}
        for status, count in self.db.execute(stmt).all():
            status_counts[status] = int(count or 0)
        counts = _counts_from_status_map(status_counts)
        total_count = counts.captured
        unique_video_count = self._profile_unique_video_count(base_filters)
        return profile_identifier, normalized_profile_url, counts, total_count, unique_video_count

    def verify_items_by_external_ids(
        self,
        *,
        aweme_ids: list[str],
        source_video_external_ids: list[str],
        capture_session_id: UUID | None = None,
        profile_url: str | None = None,
        limit: int = 100,
    ) -> list[CapturedItem]:
        requested_ids = _ordered_unique_string_values([*aweme_ids, *source_video_external_ids])
        if not requested_ids:
            return []
        stmt = (
            select(CapturedItem)
            .where(CapturedItem.source_platform == SourcePlatformEnum.DOUYIN)
            .where(CapturedItem.source_video_external_id.in_(requested_ids))
            .order_by(*_CAPTURED_ITEM_LIST_ORDER)
            .limit(limit)
        )
        if capture_session_id is not None:
            stmt = stmt.where(CapturedItem.capture_session_id == capture_session_id)
        if profile_url:
            try:
                identity = DouyinProfileAdapter().normalize_profile_identity(profile_url)
            except SourceAdapterError as exc:
                raise CaptureInboxError("invalid_profile_url", str(exc)) from exc
            profile_identifier = identity.source_profile_external_id
            stmt = stmt.join(CaptureSession, CapturedItem.capture_session_id == CaptureSession.id).where(
                or_(
                    CapturedItem.source_profile_external_id == profile_identifier,
                    CaptureSession.normalized_profile_identifier == profile_identifier,
                )
            )
        items = list(self.db.scalars(stmt))
        seen_external_ids: set[str] = set()
        deduped: list[CapturedItem] = []
        for item in items:
            external_id = item.source_video_external_id
            if not external_id or external_id in seen_external_ids:
                continue
            seen_external_ids.add(external_id)
            deduped.append(item)
        return deduped

    def retry_enrich(self, capture_session_id: UUID, *, item_ids: list[UUID] | None = None) -> list[CapturedItem]:
        session = self.get_session(capture_session_id)
        items = self._selected_items(session, item_ids=item_ids)
        seen = {
            item.dedupe_key: item
            for item in session.items
            if item.dedupe_key and item.status not in {CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED, CapturedItemStatus.FAILED}
        }
        for item in items:
            if item.status in {CapturedItemStatus.PROMOTED, CapturedItemStatus.EXCLUDED}:
                continue
            self._enrich_item(item, seen=seen, force=True)
            if item.dedupe_key and item.status != CapturedItemStatus.DUPLICATE:
                seen[item.dedupe_key] = item
        self._evaluate_items_against_intake(items, session=session)
        self._reconcile_session(session)
        self.db.commit()
        return items

    def retry_preview(self, capture_session_id: UUID, *, item_ids: list[UUID] | None = None) -> list[CapturedItem]:
        session = self.get_session(capture_session_id)
        items = self._selected_items(session, item_ids=item_ids)
        for item in items:
            if item.status in {CapturedItemStatus.PROMOTED, CapturedItemStatus.EXCLUDED}:
                continue
            self._refresh_preview_readiness(item)
        self._reconcile_session(session)
        self.db.commit()
        return items

    def get_item(self, item_id: UUID) -> CapturedItem:
        item = self.db.get(CapturedItem, item_id)
        if item is None:
            raise CaptureInboxError("captured_item_not_found", f"Captured item {item_id} was not found.")
        return item

    def stream_item_thumbnail(self, item_id: UUID) -> tuple[bytes, str]:
        item = self.get_item(item_id)
        candidates = _thumbnail_fetch_candidates(item)
        if not candidates:
            raise CaptureInboxError("thumbnail_unavailable", "No thumbnail URL candidates were found for this item.")
        last_error: str | None = None
        for candidate in candidates:
            try:
                return _fetch_remote_image(candidate)
            except Exception as exc:  # noqa: BLE001 — try next candidate
                last_error = str(exc)
        raise CaptureInboxError("thumbnail_fetch_failed", last_error or "Thumbnail fetch failed for all candidates.")

    def re_evaluate_intake(
        self,
        capture_session_id: UUID,
        *,
        item_ids: list[UUID] | None = None,
        preset_name: str | None = None,
    ) -> list[CapturedItem]:
        session = self.get_session(capture_session_id)
        items = self._selected_items(session, item_ids=item_ids)
        self._evaluate_items_against_intake(items, session=session, preset_name=preset_name)
        self._reconcile_session(session)
        self.db.commit()
        return items

    def exclude_items(self, capture_session_id: UUID, *, item_ids: list[UUID], reason: str | None = None) -> list[CapturedItem]:
        session = self.get_session(capture_session_id)
        items = self._selected_items(session, item_ids=item_ids)
        for item in items:
            if item.status == CapturedItemStatus.PROMOTED:
                continue
            item.status = CapturedItemStatus.EXCLUDED
            item.excluded_reason = reason or "Operator excluded from Capture Inbox."
        self._reconcile_session(session)
        self.db.commit()
        return items

    def delete_items(self, capture_session_id: UUID, *, item_ids: list[UUID]) -> CaptureInboxDeleteResult:
        if not item_ids:
            raise CaptureInboxError("captured_item_ids_required", "Select at least one captured item to delete.")
        session = self.get_session(capture_session_id)
        items = self._selected_items(session, item_ids=item_ids)
        deleted_item_ids: list[UUID] = []
        skipped_promoted_item_ids: list[UUID] = []
        for item in list(items):
            if item.status == CapturedItemStatus.PROMOTED:
                skipped_promoted_item_ids.append(item.id)
                continue
            deleted_item_ids.append(item.id)
            self.db.delete(item)
        if deleted_item_ids:
            self.db.flush()
            self.db.expire(session, ["items"])
        self._reconcile_session(session)
        self.db.commit()
        self.db.refresh(session)
        return CaptureInboxDeleteResult(session=session, deleted_item_ids=deleted_item_ids, skipped_promoted_item_ids=skipped_promoted_item_ids)

    def promote(self, capture_session_id: UUID, *, item_ids: list[UUID] | None = None, preset_name: str | None = None, filter_config: FilterConfig | None = None, persist: bool = True) -> CaptureInboxPromotionResult:
        session = self.get_session(capture_session_id)
        selected_items = self._selected_items(session, item_ids=item_ids)
        items, skipped = self._promotable_items_with_reasons(selected_items)
        updated_items = self._sync_existing_review_board_promotions(session, items)
        if updated_items:
            updated_ids = {item.id for item in updated_items}
            items = [item for item in items if item.id not in updated_ids]
        if not items:
            self._reconcile_session(session)
            self.db.commit()
            return CaptureInboxPromotionResult(session=session, items=updated_items, promoted_item_count=len(updated_items), candidate_created_count=0, candidate_updated_count=len(updated_items), skipped=skipped, failed=[])

        adapter_payload = self._adapter_payload_for_items(session, items)
        try:
            ingest_summary = SourceIngestService(self.db).ingest_profile(
                workspace_id=session.workspace_id,
                profile_url=session.submitted_profile_url or items[0].profile_url or "https://www.douyin.com/",
                source_platform=SourcePlatformEnum.DOUYIN,
                crawl_mode=CAPTURE_INBOX_CRAWL_MODE,
                adapter_payload_json=adapter_payload,
            )
        except SourceIngestError as exc:
            for item in items:
                item.status = CapturedItemStatus.FAILED
                item.error_code = str(exc.code)
                item.error_message = exc.message
            self._reconcile_session(session)
            self.db.commit()
            raise CaptureInboxError(str(exc.code), exc.message) from exc
        except SourceAdapterError as exc:
            for item in items:
                item.status = CapturedItemStatus.FAILED
                item.error_code = str(exc.code)
                item.error_message = exc.message
            self._reconcile_session(session)
            self.db.commit()
            raise CaptureInboxError(str(exc.code), exc.message) from exc

        if ingest_summary.status != CrawlSessionStatus.COMPLETED or ingest_summary.source_profile_id is None:
            message = ingest_summary.error_message or "Capture Inbox promotion did not complete."
            for item in items:
                item.status = CapturedItemStatus.FAILED
                item.error_code = ingest_summary.error_code or "promotion_incomplete"
                item.error_message = message
            self._reconcile_session(session)
            self.db.commit()
            raise CaptureInboxError(ingest_summary.error_code or "promotion_incomplete", message)

        before_candidates = self._candidate_ids_for_items(items)
        source_videos_for_promote = self._source_videos_by_external_id(items)
        result = CandidateEvaluationService(self.db).apply_for_source_videos(
            source_video_ids=[source_video.id for source_video in source_videos_for_promote.values()],
            preset_name=preset_name,
            filter_config=filter_config,
            persist=persist,
            shortlist_all=True,
        )
        after_candidates = self._candidate_ids_for_items(items)
        candidate_created_count = len(after_candidates - before_candidates)
        source_videos = source_videos_for_promote
        candidates_by_video = self._candidates_by_source_video_id(source_videos.values())
        crawl_session_id = UUID(str(ingest_summary.crawl_session_id)) if ingest_summary.crawl_session_id else None
        promoted_count = 0
        failed: list[CaptureInboxPromotionSkip] = []
        for item in items:
            if not (item.source_video_external_id and item.source_video_external_id in source_videos):
                item.status = CapturedItemStatus.FAILED
                item.error_code = "promotion_missing_source_video"
                item.error_message = "Promoted source video was not found after ingest."
                failed.append(CaptureInboxPromotionSkip(item_id=item.id, reason="promotion_missing_source_video"))
                continue
            source_video = source_videos[item.source_video_external_id]
            candidate = candidates_by_video.get(source_video.id)
            if candidate is None:
                candidate = self._ensure_review_board_candidate_for_source_video(source_video.id)
            if candidate is None:
                item.status = CapturedItemStatus.FAILED
                item.error_code = "promotion_missing_candidate"
                item.error_message = "Review Board candidate could not be created for promoted source video."
                failed.append(CaptureInboxPromotionSkip(item_id=item.id, reason="promotion_missing_candidate"))
                continue
            self._mark_item_promoted_to_review_board(
                item,
                source_video=source_video,
                candidate=candidate,
                crawl_session_id=crawl_session_id,
                duplicate_detected=False,
            )
            item.metadata_json = {
                **(item.metadata_json or {}),
                "promotion_result_total_count": result.total_count,
                "promotion_result_matched_count": result.matched_count,
                "promotion_persist": persist,
            }
            promoted_count += 1

        session.result_summary_json = {
            **(session.result_summary_json or {}),
            "latest_promotion": {
                "crawl_session_id": str(crawl_session_id) if crawl_session_id else None,
                "promoted_item_count": promoted_count + len(updated_items),
                "candidate_created_count": candidate_created_count,
                "candidate_updated_count": len(updated_items),
                "candidate_matched_count": result.matched_count,
                "candidate_rejected_count": result.rejected_count,
            },
        }
        self._reconcile_session(session)
        logger.info(
            "douyin_capture_session_promoted",
            extra={
                "capture_session_id": str(session.id),
                "promoted_item_count": promoted_count + len(updated_items),
                "candidate_created_count": candidate_created_count,
                "candidate_updated_count": len(updated_items),
                "crawl_session_id": str(crawl_session_id) if crawl_session_id else None,
            },
        )
        self.db.commit()
        return CaptureInboxPromotionResult(session=session, items=items + updated_items, promoted_item_count=promoted_count + len(updated_items), candidate_created_count=candidate_created_count, candidate_updated_count=len(updated_items), skipped=skipped, failed=failed)

    def _build_item(self, *, session: CaptureSession, request: DouyinExtensionCaptureRequest, raw_item: dict[str, Any], raw_item_index: int, profile_url: str, profile_external_id: str) -> CapturedItem:
        source_url = _first_string(raw_item, "source_video_url", "url", "share_url")
        source_video_external_id = _first_string(raw_item, "aweme_id", "video_id", "id") or _video_id_from_url(source_url)
        thumbnail_url = _thumbnail_url_from_payload(raw_item)
        logger.info(
            "capture_inbox_thumbnail_normalized",
            extra={
                "capture_session_id": str(session.id),
                "capture_id": session.capture_id,
                "raw_item_index": raw_item_index,
                "source_video_external_id": source_video_external_id,
                "has_thumbnail_url": bool(thumbnail_url),
                "thumbnail_candidate_count": len(raw_item.get("url_list") or []) if isinstance(raw_item.get("url_list"), list) else 0,
                "thumbnail_source_types": ",".join(raw_item.get("thumbnail_source_types") or []) if isinstance(raw_item.get("thumbnail_source_types"), list) else None,
            },
        )
        statistics = raw_item.get("statistics") if isinstance(raw_item.get("statistics"), dict) else {}
        stats = raw_item.get("stats") if isinstance(raw_item.get("stats"), dict) else {}
        merged_stats = {**stats, **statistics}
        canonical_stats = {
            "view_count": _int_or_none(_first_present(raw_item.get("view_count"), merged_stats.get("view_count"), merged_stats.get("play_count"))),
            "like_count": _int_or_none(_first_present(raw_item.get("like_count"), merged_stats.get("like_count"), merged_stats.get("digg_count"))),
            "comment_count": _int_or_none(_first_present(raw_item.get("comment_count"), merged_stats.get("comment_count"))),
            "share_count": _int_or_none(_first_present(raw_item.get("share_count"), merged_stats.get("share_count"))),
        }
        merged_stats = {**merged_stats, **{key: value for key, value in canonical_stats.items() if value is not None}}
        if merged_stats:
            raw_item = {**raw_item, "statistics": merged_stats}
            raw_item.pop("stats", None)
        initial_duration_seconds = _float_or_none(_first_present(raw_item.get("duration_seconds"), raw_item.get("duration")))
        initial_posted_at = _datetime_or_none(raw_item.get("posted_at") or raw_item.get("create_time"))
        initial_engagement_rate = _engagement_rate_or_none(
            raw_item.get("engagement_rate"),
            view_count=canonical_stats["view_count"],
            like_count=canonical_stats["like_count"],
            comment_count=canonical_stats["comment_count"],
            share_count=canonical_stats["share_count"],
        )
        share_url = _first_string(raw_item, "share_url")
        preview_status = _derive_preview_status(thumbnail_url=thumbnail_url, requested_status=_first_string(raw_item, "preview_status"))
        source_link_status = _derive_source_link_status(source_url=source_url, share_url=share_url, requested_status=_first_string(raw_item, "source_link_status"))
        media_asset_status = _derive_media_asset_status(requested_status=_first_string(raw_item, "media_asset_status"), legacy_media_status=_first_string(raw_item, "media_status"))
        media_status = _legacy_media_status(source_link_status=source_link_status, media_asset_status=media_asset_status)
        poster_aspect_ratio = _float_or_none(raw_item.get("poster_aspect_ratio"))
        thumbnail_source_type = _first_string(raw_item, "thumbnail_source_type")
        thumbnail_source_types = _string_list_or_none(raw_item.get("thumbnail_source_types"))
        thumbnail_missing_reason = _first_string(raw_item, "thumbnail_missing_reason")
        raw_metadata = raw_item.get("raw") if isinstance(raw_item.get("raw"), dict) else None
        raw_network_aweme = raw_item.get("raw_network_aweme") if isinstance(raw_item.get("raw_network_aweme"), dict) else None
        raw_detail_aweme = raw_item.get("raw_detail_aweme") if isinstance(raw_item.get("raw_detail_aweme"), dict) else None
        raw_dom_snapshot = raw_item.get("raw_dom_snapshot") if isinstance(raw_item.get("raw_dom_snapshot"), dict) else None
        raw_evidence_summary = raw_item.get("raw_evidence_summary") if isinstance(raw_item.get("raw_evidence_summary"), dict) else None
        extraction_diagnostics = raw_item.get("extraction_diagnostics") if isinstance(raw_item.get("extraction_diagnostics"), dict) else None

        normalized = CaptureMetadataNormalizer().normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=raw_network_aweme,
                raw_detail_aweme=raw_detail_aweme,
                raw_dom_snapshot=raw_dom_snapshot,
                raw_evidence_summary=raw_evidence_summary,
                existing_posted_at=initial_posted_at,
                existing_posted_text=_first_string(raw_item, "posted_text"),
                existing_duration_seconds=initial_duration_seconds,
                existing_duration_text=_first_string(raw_item, "duration_text"),
                existing_view_count=canonical_stats["view_count"],
                existing_like_count=canonical_stats["like_count"],
                existing_comment_count=canonical_stats["comment_count"],
                existing_share_count=canonical_stats["share_count"],
                existing_engagement_rate=initial_engagement_rate,
            )
        )

        posted_at = normalized.posted_at
        duration_seconds = normalized.duration_seconds
        canonical_stats = {
            "view_count": normalized.view_count,
            "like_count": normalized.like_count,
            "comment_count": normalized.comment_count,
            "share_count": normalized.share_count,
        }
        engagement_rate = normalized.engagement_rate
        capture_context = _capture_context_dict(raw_item.get("capture_context"))
        session_metadata = getattr(session, "metadata_json", None) or {}
        context_mismatch_codes = _string_list_or_none(raw_item.get("context_mismatch_codes")) or []
        capture_context = capture_context or (session_metadata.get("capture_context") if isinstance(session_metadata.get("capture_context"), dict) else {})
        follower_count = _resolve_follower_count_for_capture_item(metadata={}, raw=raw_item, session_metadata=session_metadata)
        metadata_json = {
            "capture_id": session.capture_id,
            "schema_version": request.schema_version,
            "capture_context": capture_context or session_metadata.get("capture_context"),
            "context_mismatch_codes": context_mismatch_codes,
            "follower_count": follower_count,
            "thumbnail_url": thumbnail_url,
            "poster_aspect_ratio": poster_aspect_ratio,
            "duration_text": normalized.duration_text,
            "duration_seconds": duration_seconds,
            "posted_text": normalized.posted_text,
            "posted_at": posted_at.isoformat() if posted_at else None,
            "view_count": canonical_stats["view_count"],
            "view_count_text": _first_string(raw_item, "view_count_text"),
            "like_count": canonical_stats["like_count"],
            "like_count_text": _first_string(raw_item, "like_count_text"),
            "comment_count": canonical_stats["comment_count"],
            "comment_count_text": _first_string(raw_item, "comment_count_text"),
            "share_count": canonical_stats["share_count"],
            "engagement_rate": engagement_rate,
            "duration_source": normalized.duration_source,
            "view_count_source": normalized.view_count_source,
            "like_count_source": normalized.like_count_source,
            "comment_count_source": normalized.comment_count_source,
            "share_count_source": normalized.share_count_source,
            "engagement_rate_source": normalized.engagement_rate_source,
            "has_speech": raw_item.get("has_speech"),
            "text_density": _first_string(raw_item, "text_density"),
            "has_heavy_watermark": raw_item.get("has_heavy_watermark"),
            "processing_complexity": _first_string(raw_item, "processing_complexity"),
            "copyright_risk": _first_string(raw_item, "copyright_risk"),
            "preview_status": preview_status,
            "requested_preview_status": _first_string(raw_item, "preview_status"),
            "source_link_status": source_link_status,
            "requested_source_link_status": _first_string(raw_item, "source_link_status"),
            "media_asset_status": media_asset_status,
            "requested_media_asset_status": _first_string(raw_item, "media_asset_status"),
            "media_status": media_status,
            "requested_media_status": _first_string(raw_item, "media_status"),
            "thumbnail_source_type": thumbnail_source_type,
            "thumbnail_source_types": thumbnail_source_types,
            "network_source": _first_string(raw_item, "network_source"),
            "thumbnail_source": _first_string(raw_item, "thumbnail_source"),
            "thumbnail_missing_reason": thumbnail_missing_reason,
            "posted_source": normalized.posted_source,
            "metadata_status": normalized.metadata_status,
            "time_status": normalized.time_status,
            "performance_status": normalized.performance_status,
            "processing_fit_status": normalized.processing_fit_status,
            "metadata_missing_reason": normalized.metadata_missing_reason,
            "time_missing_reason": normalized.time_missing_reason,
            "performance_missing_reason": normalized.performance_missing_reason,
            "processing_fit_missing_reason": normalized.processing_fit_missing_reason,
            "metadata_source_summary": normalized.metadata_source_summary,
            "raw": raw_metadata,
            "raw_network_aweme": raw_network_aweme,
            "raw_detail_aweme": raw_detail_aweme,
            "raw_dom_snapshot": raw_dom_snapshot,
            "raw_evidence_summary": raw_evidence_summary,
            "extraction_diagnostics": extraction_diagnostics,
        }
        explicit_nullable_keys = {
            "has_speech",
            "text_density",
            "has_heavy_watermark",
            "processing_complexity",
            "copyright_risk",
        }
        metadata_json = {
            key: value
            for key, value in metadata_json.items()
            if value is not None or key in explicit_nullable_keys
        }
        if source_video_external_id in TARGET_DEBUG_AWEME_IDS:
            checkpoint1_raw = raw_metadata.get("_target_debug_checkpoint1_json") if isinstance(raw_metadata, dict) else None
            checkpoint2_raw = raw_metadata.get("_target_debug_checkpoint2_json") if isinstance(raw_metadata, dict) else None
            try:
                checkpoint1 = json.loads(checkpoint1_raw) if isinstance(checkpoint1_raw, str) else {}
            except json.JSONDecodeError:
                checkpoint1 = {}
            try:
                checkpoint2 = json.loads(checkpoint2_raw) if isinstance(checkpoint2_raw, str) else {}
            except json.JSONDecodeError:
                checkpoint2 = {}
            checkpoint3 = {field: metadata_json.get(field) for field in TARGET_DEBUG_FIELDS}

            def _is_missing(value: Any) -> bool:
                return value is None or (isinstance(value, str) and value.strip() == "")

            def _stage_missing(stage_values: dict[str, Any]) -> bool:
                return any(_is_missing(stage_values.get(field)) for field in TARGET_DEBUG_FIELDS)

            checkpoint1_view = {field: checkpoint1.get(field) for field in TARGET_DEBUG_FIELDS}
            checkpoint2_view = {field: checkpoint2.get(field) for field in TARGET_DEBUG_FIELDS}

            if _stage_missing(checkpoint1_view):
                first_missing_stage = "checkpoint1"
                likely_next_fix_boundary = "apps/extension-douyin-capture/src/popupTransport.ts::buildDomFallbackMetadata"
            elif _stage_missing(checkpoint2_view):
                first_missing_stage = "checkpoint2"
                likely_next_fix_boundary = "apps/extension-douyin-capture/src/popupTransport.ts::buildCanonicalVideoPayload"
            elif _stage_missing(checkpoint3):
                first_missing_stage = "checkpoint3"
                likely_next_fix_boundary = "apps/api/src/services/capture_inbox_service.py::CaptureInboxService._build_item"
            else:
                first_missing_stage = "none"
                likely_next_fix_boundary = "none"

            one_shot_summary = {
                "aweme_id": source_video_external_id,
                "checkpoint1": checkpoint1_view,
                "checkpoint2": checkpoint2_view,
                "checkpoint3": checkpoint3,
                "first_missing_stage": first_missing_stage,
                "likely_next_fix_boundary": likely_next_fix_boundary,
            }
            logger.info(
                "targeted_aweme_one_shot_summary",
                extra={
                    "capture_session_id": str(session.id),
                    "capture_id": session.capture_id,
                    "raw_item_index": raw_item_index,
                    "aweme_id": source_video_external_id,
                    "one_shot_summary": one_shot_summary,
                },
            )
            existing_summaries = {}
            if isinstance(session.result_summary_json, dict):
                persisted_summaries = session.result_summary_json.get("targeted_aweme_one_shot_summaries")
                if isinstance(persisted_summaries, dict):
                    existing_summaries = {str(key): value for key, value in persisted_summaries.items() if isinstance(value, dict)}
            existing_summaries[source_video_external_id] = one_shot_summary
            session.result_summary_json = {
                **(session.result_summary_json or {}),
                "targeted_aweme_one_shot_summaries": existing_summaries,
            }
            _write_targeted_aweme_one_shot_summary_file(
                capture_session_id=str(session.id),
                capture_id=session.capture_id,
                summaries_by_aweme=existing_summaries,
            )

        logger.info(
            "capture_inbox_card_metadata_normalized",
            extra={
                "capture_session_id": str(session.id),
                "capture_id": session.capture_id,
                "raw_item_index": raw_item_index,
                "source_video_external_id": source_video_external_id,
                "preview_status": preview_status,
                "requested_preview_status": metadata_json.get("requested_preview_status"),
                "source_link_status": source_link_status,
                "requested_source_link_status": metadata_json.get("requested_source_link_status"),
                "media_asset_status": media_asset_status,
                "requested_media_asset_status": metadata_json.get("requested_media_asset_status"),
                "has_duration": duration_seconds is not None or bool(metadata_json.get("duration_text")),
                "has_posted": posted_at is not None or bool(metadata_json.get("posted_text")),
                "has_view_count": canonical_stats["view_count"] is not None or bool(metadata_json.get("view_count_text")),
                "has_like_count": canonical_stats["like_count"] is not None or bool(metadata_json.get("like_count_text")),
                "has_comment_count": canonical_stats["comment_count"] is not None or bool(metadata_json.get("comment_count_text")),
                "has_share_count": canonical_stats["share_count"] is not None,
                "has_engagement_rate": metadata_json.get("engagement_rate") is not None,
                "thumbnail_missing_reason": thumbnail_missing_reason,
                "has_network_source": bool(metadata_json.get("network_source")),
                "has_raw_metadata": bool(raw_metadata),
                "has_extraction_diagnostics": bool(extraction_diagnostics),
            },
        )
        dedupe_key = _dedupe_key(source_video_external_id, source_url)
        return CapturedItem(
            workspace_id=session.workspace_id,
            capture_session_id=session.id,
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.RAW,
            raw_item_index=raw_item_index,
            raw_payload_json=raw_item,
            source_profile_external_id=profile_external_id,
            profile_url=profile_url,
            source_video_external_id=source_video_external_id,
            source_url=source_url,
            share_url=share_url,
            caption=_first_string(raw_item, "title", "desc", "description"),
            duration_seconds=duration_seconds,
            posted_at=posted_at,
            thumbnail_url=thumbnail_url,
            preview_url=thumbnail_url,
            preview_ready=preview_status == "ready",
            media_ready=media_asset_status == "ready",
            dedupe_key=dedupe_key,
            metadata_json=metadata_json,
        )

    def _failed_item(
        self,
        *,
        session: CaptureSession,
        request: DouyinExtensionCaptureRequest,
        raw_item: dict[str, Any],
        raw_item_index: int,
        profile_url: str,
        profile_external_id: str,
        failure: CaptureInboxItemFailureSummary,
    ) -> CapturedItem:
        return CapturedItem(
            workspace_id=session.workspace_id,
            capture_session_id=session.id,
            source_platform=SourcePlatformEnum.DOUYIN,
            status=CapturedItemStatus.FAILED,
            raw_item_index=raw_item_index,
            raw_payload_json=raw_item,
            source_profile_external_id=profile_external_id,
            profile_url=profile_url,
            error_code=failure.code,
            error_message=failure.message,
            readiness_reasons_json=[failure.message],
            metadata_json={
                "capture_id": session.capture_id,
                "schema_version": request.schema_version,
                "capture_context": _capture_context_dict(raw_item.get("capture_context")) or (getattr(session, "metadata_json", None) or {}).get("capture_context"),
                "context_mismatch_codes": _string_list_or_none(raw_item.get("context_mismatch_codes")) or [],
                "failure_stage": failure.stage,
            },
        )

    def _enrich_item(self, item: CapturedItem, *, seen: dict[str, CapturedItem], force: bool = False) -> None:
        if item.dedupe_key and item.dedupe_key in seen and seen[item.dedupe_key].id != item.id:
            item.status = CapturedItemStatus.DUPLICATE
            item.duplicate_of_item_id = seen[item.dedupe_key].id
            item.readiness_reasons_json = ["Duplicate of another item in this capture session."]
            return
        if item.source_video_external_id:
            existing = self.db.scalar(
                select(SourceVideo).where(
                    SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                    SourceVideo.source_video_external_id == item.source_video_external_id,
                )
            )
            if existing is not None:
                item.existing_source_video_id = existing.id
                item.status = CapturedItemStatus.DUPLICATE
                item.readiness_reasons_json = ["Already exists in canonical SourceVideo storage."]
                return
        reasons = []
        if not item.profile_url:
            reasons.append("Missing profile URL.")
        if not item.source_url:
            reasons.append("Missing video URL.")
        if not item.source_video_external_id:
            reasons.append("Missing video external id.")
        item.preview_ready = _derive_preview_status(thumbnail_url=item.thumbnail_url or item.preview_url, requested_status=(item.metadata_json or {}).get("preview_status")) == "ready"
        item.media_ready = bool((item.metadata_json or {}).get("media_asset_status") == "ready")
        if not item.source_url and not item.source_video_external_id:
            item.status = CapturedItemStatus.FAILED
            item.error_code = "item_missing_video_identity"
            item.error_message = "Captured item is missing both video URL and external id."
            reasons.append(item.error_message)
        elif reasons:
            item.status = CapturedItemStatus.NEEDS_ENRICHMENT
        elif not item.preview_ready:
            item.status = CapturedItemStatus.PREVIEW_MISSING
            reasons.append("Preview thumbnail is missing; operator can still inspect source URL.")
        else:
            item.status = CapturedItemStatus.READY
            reasons.append("Ready for promotion.")
        item.readiness_reasons_json = reasons
        item.enrichment_json = {
            "normalized_at": datetime.now(UTC).isoformat(),
            "force": force,
            "has_profile_url": bool(item.profile_url),
            "has_source_url": bool(item.source_url),
            "has_external_id": bool(item.source_video_external_id),
            "preview_ready": item.preview_ready,
            "media_ready": item.media_ready,
        }

    def _refresh_preview_readiness(self, item: CapturedItem) -> None:
        preview_status = _derive_preview_status(thumbnail_url=item.thumbnail_url or item.preview_url, requested_status=(item.metadata_json or {}).get("preview_status"))
        item.preview_ready = preview_status == "ready"
        item.metadata_json = {**(item.metadata_json or {}), "preview_status": preview_status}
        reasons = list(item.readiness_reasons_json or [])
        if item.preview_ready:
            reasons = [reason for reason in reasons if "Preview" not in str(reason)]
            reasons.append("Preview readiness rechecked.")
            if item.status == CapturedItemStatus.PREVIEW_MISSING:
                item.status = CapturedItemStatus.READY
        else:
            item.status = CapturedItemStatus.PREVIEW_MISSING
            reasons.append("Preview remains unavailable.")
        item.readiness_reasons_json = reasons

    def _selected_items(self, session: CaptureSession, *, item_ids: list[UUID] | None) -> list[CapturedItem]:
        if not item_ids:
            return list(session.items)
        wanted = {str(item_id) for item_id in item_ids}
        return [item for item in session.items if str(item.id) in wanted]

    def _adapter_payload_for_items(self, session: CaptureSession, items: list[CapturedItem]) -> dict[str, Any]:
        display_name = None
        handle = None
        for item in items:
            metadata = item.metadata_json if isinstance(item.metadata_json, dict) else {}
            raw = item.raw_payload_json if isinstance(item.raw_payload_json, dict) else {}
            display_name = _first_present(
                display_name,
                metadata.get("profile_name"),
                metadata.get("author_display_name"),
                raw.get("profile_name"),
                raw.get("author_display_name"),
                raw.get("nickname"),
            )
            handle = _first_present(
                handle,
                metadata.get("profile_handle"),
                metadata.get("author_handle"),
                raw.get("unique_id"),
                raw.get("author_unique_id"),
            )
        if isinstance(handle, str):
            handle = handle.strip().lstrip("@") or None
        if isinstance(display_name, str):
            display_name = display_name.strip() or None
        try:
            identity = DouyinProfileAdapter().normalize_profile_identity(
                session.submitted_profile_url or items[0].profile_url or "https://www.douyin.com/"
            )
            handle = handle or identity.handle
        except Exception:
            pass
        profile = {
            "id": session.normalized_profile_identifier,
            "sec_uid": session.normalized_profile_identifier,
            "display_name": display_name,
            "nickname": display_name,
            "handle": handle,
            "unique_id": handle,
            "profile_url": session.submitted_profile_url,
        }
        videos = []
        for item in items:
            raw = dict(item.raw_payload_json or {})
            video = {
                **raw,
                **mapCaptureInboxItemToReviewCandidateMetadata(item, session=session),
            }
            videos.append({key: value for key, value in video.items() if value is not None})
        return {
            "profile": {key: value for key, value in profile.items() if value is not None},
            "videos": videos,
            "metadata": {
                "source": "douyin_capture_inbox",
                "capture_session_id": str(session.id),
                "capture_id": session.capture_id,
                "capture_source": session.capture_source,
                "promotion_model": "capture_inbox_to_canonical_review",
            },
        }

    def _evaluate_items_against_intake(
        self,
        items: list[CapturedItem],
        *,
        session: CaptureSession,
        preset_name: str | None = None,
    ) -> None:
        metadata = session.metadata_json or {}
        resolved_preset_name = preset_name or metadata.get("intake_preset_name")
        config, _, resolved_filter_preset_name = resolve_filter_config(preset_name=resolved_preset_name, override_config=None)
        resolved_name = resolved_filter_preset_name or resolved_preset_name
        for item in items:
            if item.status in {CapturedItemStatus.FAILED, CapturedItemStatus.EXCLUDED, CapturedItemStatus.DUPLICATE, CapturedItemStatus.PROMOTED}:
                item.intake_evaluation_status = IntakeEvaluationStatus.EVALUATION_ERROR
                item.matches_intake = None
                item.intake_failed_rules_json = [f"hard_rejected:{item.status}"]
                item.intake_missing_requirements_json = None
                item.intake_filter_version = "candidate_filter_v1"
                item.intake_preset_name = resolved_name
                item.last_intake_evaluated_at = datetime.now(UTC)
                item.intake_evaluation_error = None
                continue
            try:
                record = CandidateSourceRecord(
                    source_video_id=str(item.id),
                    source_profile_id=str(session.normalized_profile_identifier) if session.normalized_profile_identifier else None,
                    source_video_external_id=item.source_video_external_id or str(item.id),
                    source_url=item.source_url or item.share_url or "https://www.douyin.com/",
                    caption=item.caption,
                    posted_at=item.posted_at,
                    duration_seconds=item.duration_seconds,
                    metrics=MetricSnapshotInput(
                        view_count=_int_or_none((item.metadata_json or {}).get("view_count")),
                        like_count=_int_or_none((item.metadata_json or {}).get("like_count")),
                        comment_count=_int_or_none((item.metadata_json or {}).get("comment_count")),
                    ),
                    metadata_json=item.metadata_json or {},
                )
                result = apply_candidate_filter([record], config)
                evaluation = result.evaluations[0] if result.evaluations else None
                exclusion_reasons = list(evaluation.exclusion_reasons) if evaluation else []
                missing_requirements = [reason for reason in exclusion_reasons if "missing" in reason.lower()]
                item.matches_intake = bool(evaluation and evaluation.matched)
                if item.matches_intake:
                    item.intake_evaluation_status = IntakeEvaluationStatus.MATCHED
                elif missing_requirements:
                    item.intake_evaluation_status = IntakeEvaluationStatus.MISSING_REQUIREMENTS
                else:
                    item.intake_evaluation_status = IntakeEvaluationStatus.FILTERED_OUT
                item.intake_failed_rules_json = exclusion_reasons or None
                item.intake_missing_requirements_json = missing_requirements or None
                item.intake_filter_version = "candidate_filter_v1"
                item.intake_preset_name = resolved_name
                item.last_intake_evaluated_at = datetime.now(UTC)
                item.intake_evaluation_error = None
            except (ValueError, TypeError) as exc:
                item.intake_evaluation_status = IntakeEvaluationStatus.EVALUATION_ERROR
                item.matches_intake = None
                item.intake_failed_rules_json = None
                item.intake_missing_requirements_json = None
                item.intake_filter_version = "candidate_filter_v1"
                item.intake_preset_name = resolved_name
                item.last_intake_evaluated_at = datetime.now(UTC)
                item.intake_evaluation_error = str(exc)

    def _promotable_items_with_reasons(self, items: list[CapturedItem]) -> tuple[list[CapturedItem], list[CaptureInboxPromotionSkip]]:
        promotable: list[CapturedItem] = []
        skipped: list[CaptureInboxPromotionSkip] = []
        allowed_statuses = {CapturedItemStatus.READY, CapturedItemStatus.ENRICHED, CapturedItemStatus.PREVIEW_MISSING}
        for item in items:
            reason = self._promotion_skip_reason(item, allowed_statuses=allowed_statuses)
            if reason:
                skipped.append(CaptureInboxPromotionSkip(item_id=item.id, reason=reason))
            else:
                promotable.append(item)
        return promotable, skipped

    def repair_orphaned_handoffs_for_search(self, search: str) -> int:
        term = search.strip()
        if not term:
            return 0
        like_term = f"%{term}%"
        capture_metadata = func.coalesce(cast(CapturedItem.metadata_json, Text), "")
        items = list(
            self.db.scalars(
                select(CapturedItem)
                .options(selectinload(CapturedItem.capture_session))
                .where(
                    or_(
                        CapturedItem.source_video_external_id.ilike(like_term),
                        CapturedItem.source_url.ilike(like_term),
                        CapturedItem.share_url.ilike(like_term),
                        CapturedItem.caption.ilike(like_term),
                        CapturedItem.profile_url.ilike(like_term),
                        cast(CapturedItem.id, String).ilike(like_term),
                        capture_metadata.ilike(like_term),
                    )
                )
                .order_by(CapturedItem.updated_at.desc())
                .limit(20)
            ).unique()
        )
        repaired = 0
        for item in items:
            if item.promoted_video_candidate_id and self.db.get(VideoCandidate, item.promoted_video_candidate_id):
                continue
            source_video = self._existing_source_video_for_item(item)
            if source_video is None:
                continue
            candidate = self._ensure_review_board_candidate_for_source_video(source_video.id)
            if candidate is None:
                continue
            self._mark_item_promoted_to_review_board(
                item,
                source_video=source_video,
                candidate=candidate,
                crawl_session_id=item.promoted_crawl_session_id,
                duplicate_detected=False,
            )
            repaired += 1
        if repaired:
            self.db.commit()
            logger.info(
                "capture_inbox_orphan_handoff_repaired",
                extra={"search": term, "repaired_count": repaired},
            )
        return repaired

    def _ensure_review_board_candidate_for_source_video(self, source_video_id: UUID) -> VideoCandidate | None:
        candidate = self.db.scalar(select(VideoCandidate).where(VideoCandidate.source_video_id == source_video_id))
        if candidate is not None:
            CandidateEvaluationService(self.db).reactivate_for_review_board(candidate)
            self.db.flush()
            return candidate
        result = CandidateEvaluationService(self.db).apply_for_source_videos(
            source_video_ids=[source_video_id],
            shortlist_all=True,
            persist=True,
        )
        if result.matched_count <= 0:
            return None
        candidate = self.db.scalar(select(VideoCandidate).where(VideoCandidate.source_video_id == source_video_id))
        if candidate is not None:
            CandidateEvaluationService(self.db).reactivate_for_review_board(candidate)
            self.db.flush()
        return candidate

    def _promotion_skip_reason(self, item: CapturedItem, *, allowed_statuses: set[CapturedItemStatus]) -> str | None:
        if item.status == CapturedItemStatus.PROMOTED:
            if item.promoted_video_candidate_id:
                candidate = self.db.get(VideoCandidate, item.promoted_video_candidate_id)
                if candidate is None or candidate.status == CandidateStatus.ARCHIVED:
                    return None
            else:
                return None
            return "already_promoted"
        if item.status in {CapturedItemStatus.FAILED, CapturedItemStatus.EXCLUDED, CapturedItemStatus.DUPLICATE}:
            return f"status_{item.status.value.lower()}"
        if item.status not in allowed_statuses:
            return "not_ready"
        if not item.source_video_external_id and not (item.source_url or item.share_url):
            return "missing_source_identity"
        if not (item.thumbnail_url or _thumbnail_url_from_payload(item.raw_payload_json or {})):
            return "missing_metadata"
        if not (item.caption or (item.raw_payload_json or {}).get("desc") or (item.raw_payload_json or {}).get("title")):
            return "missing_metadata"
        return None

    def _sync_existing_review_board_promotions(self, session: CaptureSession, items: list[CapturedItem]) -> list[CapturedItem]:
        updated_items: list[CapturedItem] = []
        for item in items:
            source_video = self._existing_source_video_for_item(item)
            candidate = None
            if source_video is not None:
                candidate = self.db.scalar(select(VideoCandidate).where(VideoCandidate.source_video_id == source_video.id))
            if candidate is None:
                candidate = self._existing_candidate_for_capture_item(item)
                source_video = getattr(candidate, "source_video", None) if candidate is not None else source_video
            if candidate is None or source_video is None:
                continue
            self._enrich_existing_review_board_candidate_from_capture_item(session, item, source_video=source_video, candidate=candidate)
            self._mark_item_promoted_to_review_board(item, source_video=source_video, candidate=candidate, crawl_session_id=None, duplicate_detected=True)
            updated_items.append(item)
        return updated_items

    def _enrich_existing_review_board_candidate_from_capture_item(
        self,
        session: CaptureSession,
        item: CapturedItem,
        *,
        source_video: SourceVideo,
        candidate: VideoCandidate,
    ) -> None:
        snapshot = buildCaptureInboxSourceMetadataSnapshot(item, session=session, snapshot_source="capture_inbox_duplicate_promote")
        comparison = buildCaptureToReviewComparison(capture_snapshot=snapshot, review_metadata=snapshot, candidate_id=candidate.id, matched_by="duplicate_promote")
        metadata = {**snapshot, "source_metadata": snapshot, "capture_to_review_comparison": comparison}
        source_video.metadata_json = {**(source_video.metadata_json or {}), **metadata, "review_board_upsert_source": "capture_inbox_duplicate_promote"}
        source_video.raw_payload_json = {**(source_video.raw_payload_json or {}), **(item.raw_payload_json or {})}
        source_video.source_url = metadata.get("source_url") or source_video.source_url
        source_video.caption = metadata.get("caption") or source_video.caption
        posted_at = _datetime_or_none(metadata.get("posted_at"))
        source_video.posted_at = posted_at or source_video.posted_at
        duration_seconds = _float_or_none(metadata.get("duration_seconds"))
        source_video.duration_seconds = duration_seconds if duration_seconds is not None else source_video.duration_seconds
        candidate.metadata_json = {
            **(candidate.metadata_json or {}),
            **metadata,
            "review_board_upserted_at": datetime.now(UTC).isoformat(),
            "review_board_upsert_source": "capture_inbox_duplicate_promote",
        }
        CandidateEvaluationService(self.db).reactivate_for_review_board(candidate)
        CandidateEvaluationService(self.db).hydrateReviewCandidateFromCaptureItem(candidate, persist=True)
        self.db.flush()

    def _existing_candidate_for_capture_item(self, item: CapturedItem) -> VideoCandidate | None:
        capture_item_id = str(item.id)
        return self.db.scalar(
            select(VideoCandidate)
            .options(selectinload(VideoCandidate.source_video))
            .where(VideoCandidate.metadata_json["capture_item_id"].as_string() == capture_item_id)
        )

    def _existing_source_video_for_item(self, item: CapturedItem) -> SourceVideo | None:
        if item.promoted_source_video_id:
            source_video = self.db.get(SourceVideo, item.promoted_source_video_id)
            if source_video is not None:
                return source_video
        if item.existing_source_video_id:
            source_video = self.db.get(SourceVideo, item.existing_source_video_id)
            if source_video is not None:
                return source_video
        if item.source_video_external_id:
            source_video = self.db.scalar(
                select(SourceVideo).where(
                    SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                    SourceVideo.source_video_external_id == item.source_video_external_id,
                )
            )
            if source_video is not None:
                return source_video
        source_url = item.source_url or item.share_url
        if source_url:
            return self.db.scalar(
                select(SourceVideo).where(
                    SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                    SourceVideo.source_url == source_url,
                )
            )
        return None

    def _mark_item_promoted_to_review_board(
        self,
        item: CapturedItem,
        *,
        source_video: SourceVideo,
        candidate: VideoCandidate | None,
        crawl_session_id: UUID | None,
        duplicate_detected: bool,
    ) -> None:
        if candidate is None:
            return
        item.promoted_source_video_id = source_video.id
        item.promoted_video_candidate_id = candidate.id if candidate else None
        item.promoted_crawl_session_id = crawl_session_id or item.promoted_crawl_session_id
        item.status = CapturedItemStatus.PROMOTED
        snapshot = buildCaptureInboxSourceMetadataSnapshot(item, session=item.capture_session, snapshot_source="capture_inbox_promote")
        if candidate is not None:
            CandidateEvaluationService(self.db).reactivate_for_review_board(candidate)
            comparison = buildCaptureToReviewComparison(capture_snapshot=snapshot, review_metadata=snapshot, candidate_id=candidate.id, matched_by="promote")
            candidate.metadata_json = {
                **(candidate.metadata_json or {}),
                **snapshot,
                "source_metadata": snapshot,
                "capture_to_review_comparison": comparison,
                "review_board_upserted_at": datetime.now(UTC).isoformat(),
                "review_board_upsert_source": "capture_inbox_promote",
            }
            source_video.metadata_json = {
                **(source_video.metadata_json or {}),
                **snapshot,
                "source_metadata": snapshot,
                "capture_to_review_comparison": comparison,
                "review_board_upsert_source": "capture_inbox_promote",
            }
        item.metadata_json = {
            **(item.metadata_json or {}),
            "source_metadata": snapshot,
            "source_metadata_version": "22F-1F",
            "metadata_snapshot_created": True,
            "review_status": "promoted",
            "promoted_at": datetime.now(UTC).isoformat(),
            "promoted_to_review_board_id": str(item.promoted_video_candidate_id) if item.promoted_video_candidate_id else None,
            "review_board_handoff_verified": item.promoted_video_candidate_id is not None,
            "review_board_item_id": str(item.promoted_video_candidate_id) if item.promoted_video_candidate_id else None,
            "review_board_duplicate_detected": duplicate_detected,
        }

    def _candidate_ids_for_items(self, items: list[CapturedItem]) -> set[UUID]:
        source_videos = self._source_videos_by_external_id(items)
        return {candidate.id for candidate in self._candidates_by_source_video_id(source_videos.values()).values()}

    def _source_videos_by_external_id(self, items: list[CapturedItem]) -> dict[str, SourceVideo]:
        external_ids = [item.source_video_external_id for item in items if item.source_video_external_id]
        if not external_ids:
            return {}
        rows = self.db.scalars(
            select(SourceVideo).where(
                SourceVideo.source_platform == SourcePlatformEnum.DOUYIN,
                SourceVideo.source_video_external_id.in_(external_ids),
            )
        )
        return {row.source_video_external_id: row for row in rows}

    def _candidates_by_source_video_id(self, source_videos) -> dict[UUID, VideoCandidate]:
        source_video_ids = [video.id for video in source_videos]
        if not source_video_ids:
            return {}
        rows = self.db.scalars(select(VideoCandidate).where(VideoCandidate.source_video_id.in_(source_video_ids)))
        return {row.source_video_id: row for row in rows}

    def _reconcile_session(self, session: CaptureSession) -> None:
        items = list(getattr(session, "items", []) or [])
        if not items and getattr(session, "id", None):
            items = list(
                self.db.scalars(
                    select(CapturedItem).where(CapturedItem.capture_session_id == session.id)
                )
            )
            if hasattr(session, "items"):
                try:
                    session.items = items
                except Exception:
                    pass
        self._apply_session_counts(session, items, persist_summary=True)

    def _apply_session_counts(self, session: CaptureSession, items: list[CapturedItem], *, persist_summary: bool) -> None:
        session.captured_item_count = len(items)
        session.normalized_item_count = sum(1 for item in items if item.status in {CapturedItemStatus.ENRICHED, CapturedItemStatus.READY, CapturedItemStatus.PREVIEW_MISSING, CapturedItemStatus.PROMOTED})
        session.duplicate_item_count = sum(1 for item in items if item.status == CapturedItemStatus.DUPLICATE)
        session.ready_item_count = sum(1 for item in items if item.status == CapturedItemStatus.READY)
        session.skipped_item_count = sum(1 for item in items if item.status == CapturedItemStatus.EXCLUDED)
        session.promoted_item_count = sum(1 for item in items if item.status == CapturedItemStatus.PROMOTED)
        session.candidate_created_count = sum(1 for item in items if item.promoted_video_candidate_id is not None)
        session.failed_item_count = sum(1 for item in items if item.status == CapturedItemStatus.FAILED)
        if session.failed_item_count and session.failed_item_count == len(items):
            session.status = CaptureSessionStatus.FAILED
        elif session.promoted_item_count and session.promoted_item_count >= max(1, session.ready_item_count + session.promoted_item_count):
            session.status = CaptureSessionStatus.PROMOTED
        elif session.promoted_item_count:
            session.status = CaptureSessionStatus.PARTIALLY_PROMOTED
        else:
            session.status = CaptureSessionStatus.READY_FOR_REVIEW
        if persist_summary:
            session.finished_at = datetime.now(UTC)
            session.result_summary_json = {
                **(session.result_summary_json or {}),
                "reconciliation": {
                    "visible_item_count": session.visible_item_count,
                    "captured_item_count": session.captured_item_count,
                    "normalized_item_count": session.normalized_item_count,
                    "duplicate_item_count": session.duplicate_item_count,
                    "ready_item_count": session.ready_item_count,
                    "skipped_item_count": session.skipped_item_count,
                    "promoted_item_count": session.promoted_item_count,
                    "candidate_created_count": session.candidate_created_count,
                    "failed_item_count": session.failed_item_count,
                },
            }


    def _filter_items(
        self,
        items: list[CapturedItem],
        *,
        search: str | None,
        advanced_filter: CaptureInboxAdvancedFilterRequest | None,
    ) -> list[CapturedItem]:
        query = (search or "").strip().lower()
        results: list[CapturedItem] = []
        for item in items:
            if query:
                haystack = " ".join(
                    value
                    for value in [
                        item.caption or "",
                        item.source_video_external_id or "",
                        item.source_url or "",
                        item.share_url or "",
                    ]
                ).lower()
                if query not in haystack:
                    continue
            if advanced_filter and not self._matches_advanced_filter(item, advanced_filter):
                continue
            results.append(item)
        return results

    def _matches_advanced_filter(self, item: CapturedItem, filters: CaptureInboxAdvancedFilterRequest) -> bool:
        metadata = item.metadata_json or {}

        def int_value(key: str) -> int | None:
            return _int_or_none(metadata.get(key))

        def float_value(key: str) -> float | None:
            return _float_or_none(metadata.get(key))

        posted_at = item.posted_at
        if filters.from_date and (posted_at is None or posted_at < filters.from_date):
            return False
        if filters.to_date and (posted_at is None or posted_at > filters.to_date):
            return False

        checks: list[tuple[int | float | None, int | float | None, int | float | None]] = [
            (int_value("view_count"), filters.min_views, filters.max_views),
            (int_value("like_count"), filters.min_likes, filters.max_likes),
            (int_value("comment_count"), filters.min_comments, filters.max_comments),
            (int_value("share_count"), filters.min_shares, filters.max_shares),
            (float_value("engagement_rate"), filters.min_engagement_rate, filters.max_engagement_rate),
            (item.duration_seconds, filters.min_duration_seconds, filters.max_duration_seconds),
        ]
        for value, min_value, max_value in checks:
            if min_value is not None and (value is None or value < min_value):
                return False
            if max_value is not None and (value is None or value > max_value):
                return False

        has_speech = metadata.get("has_speech")
        if filters.speech is True and has_speech is not True:
            return False
        if filters.speech is False and has_speech is not False:
            return False

        density = str(metadata.get("text_density") or "").lower()
        ranks = {"": 0, "low": 1, "medium": 2, "high": 3}
        if filters.max_text_density and ranks.get(density, 0) > ranks.get(filters.max_text_density, 0):
            return False

        if filters.exclude_heavy_watermark and metadata.get("has_heavy_watermark") is True:
            return False
        complexity_excluded = filters.exclude_high_complexity or filters.exclude_high_processing_complexity
        if complexity_excluded and str(metadata.get("processing_complexity") or "").lower() in {"high", "blocking"}:
            return False
        if filters.exclude_high_copyright_risk and str(metadata.get("copyright_risk") or "").lower() in {"high", "true"}:
            return False

        return True


def reconciliation_from_session(session: CaptureSession) -> dict[str, int]:
    return {
        "visible_item_count": session.visible_item_count,
        "captured_item_count": session.captured_item_count,
        "normalized_item_count": session.normalized_item_count,
        "duplicate_item_count": session.duplicate_item_count,
        "ready_item_count": session.ready_item_count,
        "skipped_item_count": session.skipped_item_count,
        "promoted_item_count": session.promoted_item_count,
        "candidate_created_count": session.candidate_created_count,
        "failed_item_count": session.failed_item_count,
    }


def buildCaptureInboxSourceMetadataSnapshot(item: CapturedItem, *, session: CaptureSession | None = None, snapshot_source: str = "capture_inbox_promote") -> dict[str, Any]:
    metadata = mapCaptureInboxItemToReviewCandidateMetadata(item, session=session)
    snapshot = {
        **metadata,
        "source": "douyin",
        "source_module": "capture_inbox",
        "source_metadata_version": "22F-1H-2",
        "snapshot_created_at": datetime.now(UTC).isoformat(),
        "snapshot_source": snapshot_source,
    }
    return {key: value for key, value in snapshot.items() if value is not None}


def buildCaptureToReviewComparison(*, capture_snapshot: dict[str, Any], review_metadata: dict[str, Any], candidate_id: Any = None, matched_by: str | None = None) -> dict[str, Any]:
    fields = {}
    for field in ("reup_score", "estimated_views_display", "like_count", "comment_count", "share_count", "posted_display", "duration_text"):
        capture_value = capture_snapshot.get(field)
        review_value = review_metadata.get(field)
        fields[field] = {"capture": capture_value, "review": review_value, "match": capture_value == review_value}
    return {
        "traceVersion": "22F-1F",
        "captureItemId": capture_snapshot.get("capture_item_id"),
        "candidateId": str(candidate_id) if candidate_id is not None else None,
        "awemeId": capture_snapshot.get("aweme_id"),
        "matchedBy": matched_by,
        "fields": fields,
    }


def mapCaptureInboxItemToReviewCandidateMetadata(item: CapturedItem, *, session: CaptureSession | None = None) -> dict[str, Any]:
    raw = dict(item.raw_payload_json or {})
    metadata = item.metadata_json or {}
    stats = raw.get("statistics") if isinstance(raw.get("statistics"), dict) else {}
    aweme_id = item.source_video_external_id or raw.get("aweme_id") or raw.get("video_id")
    source_url = item.source_url or raw.get("source_video_url") or raw.get("url")
    caption = _capture_item_title_from_payloads(caption=item.caption, metadata=metadata, raw=raw, aweme_id=aweme_id)
    estimated_views = _canonical_estimated_views_for_capture_item(item, metadata=metadata, raw=raw, stats=stats)
    reup_score = _canonical_reup_score_for_capture_item(item, metadata=metadata, raw=raw, stats=stats, estimated_views=estimated_views)
    posted_display_exact = getCaptureInboxPostedDisplayExact(item)
    posted_display_source = _first_present(
        metadata.get("posted_display_source"),
        posted_display_exact["source"],
        metadata.get("posted_source"),
        raw.get("posted_source"),
    )
    mapped = {
        "capture_item_id": str(item.id),
        "capture_session_id": str(session.id) if session is not None else str(item.capture_session_id),
        "source": "douyin",
        "source_module": "capture_inbox",
        "aweme_id": aweme_id,
        "source_video_external_id": aweme_id,
        "source_video_url": source_url,
        "source_url": source_url,
        "video_url": source_url,
        "profile_url": item.profile_url or (session.submitted_profile_url if session is not None else None),
        "profile_name": _first_present(metadata.get("profile_name"), metadata.get("author_display_name"), raw.get("profile_name"), raw.get("author_display_name")),
        "share_url": item.share_url or raw.get("share_url"),
        "desc": caption,
        "description": caption,
        "caption": caption,
        "title": caption,
        "duration_seconds": item.duration_seconds,
        "duration_text": _first_present(metadata.get("duration_text"), raw.get("duration_text")),
        "duration_source": _first_present(metadata.get("duration_source"), raw.get("duration_source")),
        "posted_at": item.posted_at.isoformat() if item.posted_at else raw.get("posted_at") or raw.get("create_time"),
        "posted_text": _first_present(metadata.get("posted_text"), raw.get("posted_text")),
        "posted_text_raw": _first_present(metadata.get("posted_text_raw"), raw.get("posted_text_raw"), metadata.get("posted_text"), raw.get("posted_text")),
        "posted_display": _first_present(posted_display_exact["value"], metadata.get("posted_display"), metadata.get("posted_text"), raw.get("posted_display"), raw.get("posted_text")),
        "posted_display_exact": posted_display_exact["value"],
        "posted_display_source": posted_display_source,
        "posted_source": _first_present(metadata.get("posted_source"), raw.get("posted_source")),
        "thumbnail_url": item.thumbnail_url or _thumbnail_url_from_payload(raw),
        "view_count": _first_present(metadata.get("view_count"), raw.get("view_count"), stats.get("view_count"), stats.get("play_count")),
        "view_count_text": _first_present(metadata.get("view_count_text"), raw.get("view_count_text")),
        "estimated_views_text_raw": _first_present(metadata.get("estimated_views_text_raw"), raw.get("estimated_views_text_raw")),
        "estimated_views_display": estimated_views.get("estimated_views_display"),
        "estimated_views_min": estimated_views.get("estimated_views_min"),
        "estimated_views_max": estimated_views.get("estimated_views_max"),
        "estimated_views_mid": estimated_views.get("estimated_views_mid"),
        "estimated_views_parse_confidence": estimated_views.get("estimated_views_parse_confidence"),
        "like_count": _first_present(metadata.get("like_count"), raw.get("like_count"), stats.get("like_count"), stats.get("digg_count")),
        "like_count_text": _first_present(metadata.get("like_count_text"), raw.get("like_count_text")),
        "comment_count": _first_present(metadata.get("comment_count"), raw.get("comment_count"), stats.get("comment_count")),
        "comment_count_text": _first_present(metadata.get("comment_count_text"), raw.get("comment_count_text")),
        "share_count": _first_present(metadata.get("share_count"), raw.get("share_count"), stats.get("share_count")),
        "share_count_text": _first_present(metadata.get("share_count_text"), raw.get("share_count_text")),
        "favorite_count": _first_present(metadata.get("favorite_count"), raw.get("favorite_count"), stats.get("favorite_count"), stats.get("collect_count")),
        "favorite_count_text": _first_present(metadata.get("favorite_count_text"), raw.get("favorite_count_text")),
        "follower_count": _resolve_follower_count_for_capture_item(metadata=metadata, raw=raw, session_metadata=(session.metadata_json if session is not None else None)),
        "follower_count_text": _first_present(metadata.get("follower_count_text"), raw.get("follower_count_text")),
        "engagement_score": reup_score.get("engagement_score"),
        "engagement_rate": reup_score.get("engagement_rate"),
        "engagement_rate_basis": reup_score.get("engagement_rate_basis"),
        "reup_score": reup_score.get("reup_score"),
        "reup_score_label": reup_score.get("reup_score_label"),
        "reup_score_level": reup_score.get("reup_score_level"),
        "reup_score_components": reup_score.get("reup_score_components"),
        "reup_score_reasons": reup_score.get("reup_score_reasons"),
        "preview_status": metadata.get("preview_status") or raw.get("preview_status"),
        "media_status": metadata.get("media_status") or raw.get("media_status"),
        "review_board_status": "pending_review",
        "review_status": "pending_review",
        "decision_status": "pending_review",
        "preset": _first_present(metadata.get("intake_preset_name"), raw.get("intake_preset_name")),
        "matched_presets": _first_present(metadata.get("matched_presets"), raw.get("matched_presets")),
        "has_thumbnail": metadata.get("has_thumbnail"),
        "has_posted": metadata.get("has_posted"),
        "has_duration": metadata.get("has_duration"),
        "has_estimated_views": metadata.get("has_estimated_views") if "has_estimated_views" in metadata else metadata.get("has_views"),
        "has_likes": metadata.get("has_likes"),
        "has_comments": metadata.get("has_comments"),
        "has_shares": metadata.get("has_shares"),
        "has_all_core_metadata": metadata.get("has_all_core_metadata"),
        "missing_metadata_fields": metadata.get("missing_metadata_fields"),
        "statistics": stats,
    }
    return {key: value for key, value in mapped.items() if value is not None}


def getCaptureInboxPostedDisplayExact(item: CapturedItem) -> dict[str, str | None]:
    """Mirror Capture Inbox card Posted precedence for Review Board snapshots."""
    raw = dict(item.raw_payload_json or {})
    metadata = item.metadata_json or {}
    display = _string_from_payloads("posted_display_exact", metadata, raw)
    if display:
        return {"value": display, "source": "capture_item.metadata_json.posted_display_exact" if metadata.get("posted_display_exact") else "capture_item.raw_payload_json.posted_display_exact"}
    if item.posted_at is not None:
        return {"value": _capture_inbox_card_datetime_display(item.posted_at), "source": "apps/web/src/lib/captureInboxCanonical.ts:resolvePosted->formatDateTime(item.posted_at)"}
    for payload_name, payload in (("display_metadata", metadata.get("display_metadata")), ("source_metadata", metadata.get("source_metadata")), ("metadata", metadata.get("metadata"))):
        if isinstance(payload, dict):
            display = _string_from_payloads("posted_display", payload)
            if display:
                return {"value": display, "source": f"capture_item.metadata_json.{payload_name}.posted_display"}
    display = _string_from_payloads("posted_text_raw", metadata, raw) or _string_from_payloads("raw_posted_text", metadata, raw)
    if display:
        source_key = "posted_text_raw" if _string_from_payloads("posted_text_raw", metadata, raw) else "raw_posted_text"
        return {"value": display, "source": f"capture_item.{source_key}"}
    display = _string_from_payloads("posted_display", metadata, raw) or _string_from_payloads("posted_text", metadata, raw)
    if display:
        return {"value": display, "source": "capture_item.metadata_json.posted_display" if metadata.get("posted_display") else "capture_item.posted_text"}
    return {"value": None, "source": "no_exact_capture_posted_display"}


def _capture_inbox_card_datetime_display(value: datetime) -> str:
    local_value = value.astimezone(ZoneInfo("Asia/Bangkok")).replace(microsecond=0)
    return f"{local_value:%H:%M:%S} {local_value.day}/{local_value.month}/{local_value.year}"


def _string_from_payloads(key: str, *payloads: dict[str, Any]) -> str | None:
    for payload in payloads:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_string(payload: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _capture_context_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json", exclude_none=True)
    if isinstance(value, dict) and isinstance(value.get("capture_context"), dict):
        value = value["capture_context"]
    if not isinstance(value, dict):
        return {}
    allowed = {"capture_id", "workspace_id", "tab_id", "page_url", "page_url_normalized", "profile_url", "profile_external_id", "captured_at", "cache_scope_key"}
    return {key: raw for key, raw in value.items() if key in allowed and raw is not None}


def _context_mismatch_codes(session_context: dict[str, Any], item_context_value: Any, *, workspace_id: UUID) -> list[str]:
    item_context = _capture_context_dict(item_context_value)
    if not item_context:
        return []
    codes: list[str] = []
    if item_context.get("workspace_id") and str(item_context.get("workspace_id")) != str(workspace_id):
        codes.append("project_mismatch")
    if item_context.get("capture_id") and session_context.get("capture_id") and item_context.get("capture_id") != session_context.get("capture_id"):
        codes.append("session_mismatch")
    if item_context.get("tab_id") is not None and session_context.get("tab_id") is not None and item_context.get("tab_id") != session_context.get("tab_id"):
        codes.append("tab_mismatch")
    if _contexts_differ(item_context, session_context, key="profile_external_id") or _contexts_differ(item_context, session_context, key="profile_url", normalize_url=True):
        codes.append("profile_mismatch")
    if _contexts_differ(item_context, session_context, key="page_url_normalized") or _contexts_differ(item_context, session_context, key="page_url", normalize_url=True):
        codes.append("page_mismatch")
    existing_codes = _string_list_or_none(item_context_value.get("context_mismatch_codes")) if isinstance(item_context_value, dict) else None
    for code in existing_codes or []:
        if code not in codes:
            codes.append(code)
    if codes and "context_mismatch" not in codes:
        codes.insert(0, "context_mismatch")
    return codes


def _contexts_differ(left: dict[str, Any], right: dict[str, Any], *, key: str, normalize_url: bool = False) -> bool:
    left_value = left.get(key)
    right_value = right.get(key)
    if left_value in {None, ""} or right_value in {None, ""}:
        return False
    if normalize_url:
        left_value = _normalize_context_url(str(left_value))
        right_value = _normalize_context_url(str(right_value))
    return str(left_value) != str(right_value)


def _ordered_unique_string_values(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result



def _normalize_context_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path.rstrip('/')}"


def _canonical_estimated_views_for_capture_item(item: CapturedItem, *, metadata: dict[str, Any], raw: dict[str, Any], stats: dict[str, Any]) -> dict[str, Any]:
    display = _first_present(metadata.get("estimated_views_display"), metadata.get("estimated_views_text"), metadata.get("estimated_views"), metadata.get("view_count_text"), raw.get("estimated_views_display"), raw.get("estimated_views_text"), raw.get("estimated_views"), raw.get("view_count_text"))
    min_value = _int_or_none(_first_present(metadata.get("estimated_views_min"), raw.get("estimated_views_min")))
    max_value = _int_or_none(_first_present(metadata.get("estimated_views_max"), raw.get("estimated_views_max")))
    mid_value = _int_or_none(_first_present(metadata.get("estimated_views_mid"), raw.get("estimated_views_mid"), metadata.get("view_count"), raw.get("view_count"), stats.get("view_count"), stats.get("play_count")))
    confidence = _first_present(metadata.get("estimated_views_parse_confidence"), raw.get("estimated_views_parse_confidence"))
    if display or min_value is not None or max_value is not None or mid_value is not None:
        return {
            "estimated_views_display": display,
            "estimated_views_min": min_value,
            "estimated_views_max": max_value,
            "estimated_views_mid": mid_value,
            "estimated_views_parse_confidence": confidence or "high",
            "estimated_views_source": "canonical",
        }

    like_count = _int_or_none(_first_present(metadata.get("like_count"), raw.get("like_count"), stats.get("like_count"), stats.get("digg_count")))
    view_count = _int_or_none(_first_present(metadata.get("view_count"), raw.get("view_count"), stats.get("view_count"), stats.get("play_count")))
    can_derive_from_likes = metadata.get("metadata_status") == "complete" or metadata.get("performance_status") == "captured"
    if view_count is not None or like_count is None or like_count <= 0 or not can_derive_from_likes:
        return {"estimated_views_parse_confidence": confidence or "none"}

    min_value = round(like_count * 20)
    mid_value = round(like_count * 33)
    max_value = round(like_count * 100)
    return {
        "estimated_views_display": f"{_format_compact_number(min_value)}-{_format_compact_number(max_value)}",
        "estimated_views_min": min_value,
        "estimated_views_max": max_value,
        "estimated_views_mid": mid_value,
        "estimated_views_parse_confidence": "low",
        "estimated_views_source": "derived_from_likes",
    }


def _canonical_reup_score_for_capture_item(item: CapturedItem, *, metadata: dict[str, Any], raw: dict[str, Any], stats: dict[str, Any], estimated_views: dict[str, Any]) -> dict[str, Any]:
    like_count = _int_or_none(_first_present(metadata.get("like_count"), raw.get("like_count"), stats.get("like_count"), stats.get("digg_count")))
    comment_count = _int_or_none(_first_present(metadata.get("comment_count"), raw.get("comment_count"), stats.get("comment_count")))
    share_count = _int_or_none(_first_present(metadata.get("share_count"), raw.get("share_count"), stats.get("share_count")))
    favorite_count = _int_or_none(_first_present(metadata.get("favorite_count"), raw.get("favorite_count"), stats.get("favorite_count"), stats.get("collect_count")))
    follower_count = _resolve_follower_count_for_capture_item(metadata=metadata, raw=raw)
    engagement_score = sum(value or 0 for value in (like_count, comment_count, share_count, favorite_count))
    views_mid = _int_or_none(estimated_views.get("estimated_views_mid"))
    view_count = _int_or_none(_first_present(metadata.get("view_count"), raw.get("view_count"), stats.get("view_count"), stats.get("play_count")))
    existing_engagement_rate = _float_or_none(_first_present(metadata.get("engagement_rate"), raw.get("engagement_rate")))
    engagement_basis = views_mid if views_mid and views_mid > 0 else view_count if view_count and view_count > 0 else None
    engagement_rate = existing_engagement_rate if existing_engagement_rate is not None else round(engagement_score / engagement_basis, 6) if engagement_score > 0 and engagement_basis else None
    engagement_rate_basis = "existing" if existing_engagement_rate is not None else "estimated_views_mid" if views_mid and views_mid > 0 else "view_count" if view_count and view_count > 0 else "none"

    has_thumbnail = bool(item.thumbnail_url or metadata.get("thumbnail_url") or raw.get("thumbnail_url"))
    duration_seconds = _float_or_none(_first_present(item.duration_seconds, metadata.get("duration_seconds"), raw.get("duration_seconds")))
    posted_at = _datetime_or_none(_first_present(item.posted_at, metadata.get("posted_at"), raw.get("posted_at"), raw.get("create_time")))
    has_posted = posted_at is not None or bool(_first_present(metadata.get("posted_display"), metadata.get("posted_text"), raw.get("posted_display"), raw.get("posted_text")))
    has_views = views_mid is not None or view_count is not None or bool(estimated_views.get("estimated_views_display"))
    has_any_metric = any((value or 0) > 0 for value in (like_count, comment_count, share_count, favorite_count))
    missing = []
    if not has_thumbnail:
        missing.append("thumbnail")
    if not has_posted:
        missing.append("posted")
    if duration_seconds is None:
        missing.append("duration")
    if not has_views:
        missing.append("views")
    if like_count is None:
        missing.append("likes")
    if comment_count is None:
        missing.append("comments")
    if share_count is None:
        missing.append("shares")

    outlier_bonus = _score_outlier_bonus(views_mid, follower_count)
    components = {
        "performance": _score_performance(views_mid),
        "engagement": _score_engagement(views_mid, like_count, comment_count),
        "virality_retention": _score_virality_retention(views_mid, share_count, favorite_count),
        "duration_fit": _score_duration_fit(duration_seconds),
        "recency": _score_recency(posted_at),
        "metadata_quality": max(0, 10 - len(missing) * 2),
        "penalty": _score_penalty(item, has_thumbnail, duration_seconds is not None, has_posted, has_views, has_any_metric, metadata=metadata),
        "outlier_bonus": outlier_bonus,
    }
    almost_no_metadata = not has_thumbnail and duration_seconds is None and not has_posted and not has_views and not has_any_metric
    base_score = sum(value for key, value in components.items() if key != "outlier_bonus")
    score = 0 if almost_no_metadata else round(max(0, min(100, base_score + outlier_bonus)))
    label, level = _label_for_score(score, missing)
    reasons = _score_reasons(
        label=label,
        views=views_mid,
        like_count=like_count,
        comment_count=comment_count,
        share_count=share_count,
        favorite_count=favorite_count,
        follower_count=follower_count,
        duration_seconds=duration_seconds,
        missing=missing,
        has_thumbnail=has_thumbnail,
        has_posted=has_posted,
        has_views=has_views,
        outlier_bonus=outlier_bonus,
    )
    return {
        "reup_score": score,
        "reup_score_label": label,
        "reup_score_level": level,
        "reup_score_components": components,
        "reup_score_reasons": reasons,
        "engagement_score": engagement_score if engagement_score > 0 else None,
        "engagement_rate": engagement_rate,
        "engagement_rate_basis": engagement_rate_basis,
        "missing_metadata_fields": missing,
        "has_all_core_metadata": len(missing) == 0,
    }


def _format_compact_number(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"
    if value >= 1_000:
        return f"{value / 1_000:.1f}".rstrip("0").rstrip(".") + "K"
    return str(value)


def _resolve_follower_count_for_capture_item(
    *,
    metadata: dict[str, Any] | None = None,
    raw: dict[str, Any] | None = None,
    session_metadata: dict[str, Any] | None = None,
) -> int | None:
    metadata = metadata or {}
    raw = raw or {}
    session_metadata = session_metadata or {}
    capture_context = session_metadata.get("capture_context") if isinstance(session_metadata.get("capture_context"), dict) else {}
    author = metadata.get("author") if isinstance(metadata.get("author"), dict) else {}
    profile = metadata.get("profile") if isinstance(metadata.get("profile"), dict) else {}
    return _int_or_none(
        _first_present(
            metadata.get("follower_count"),
            raw.get("follower_count"),
            capture_context.get("follower_count"),
            session_metadata.get("follower_count"),
            author.get("follower_count"),
            profile.get("follower_count"),
        )
    )


def _score_performance(views: int | None) -> int:
    if views is None or views <= 0:
        return 0
    if 100_000 <= views <= 3_000_000:
        return 20
    if 10_000 <= views < 100_000:
        return 15
    if 3_000_000 < views <= 10_000_000:
        return 10
    if views > 10_000_000:
        return 5
    if views < 10_000:
        return 2
    return 0


def _score_engagement(views: int | None, like_count: int | None, comment_count: int | None) -> int:
    if views is None or views <= 0:
        return 0
    rate = ((like_count or 0) + (comment_count or 0)) / views
    points = 2
    if rate >= 0.08:
        points = 20
    elif rate >= 0.05:
        points = 15
    elif rate >= 0.03:
        points = 10
    elif rate >= 0.015:
        points = 5
    if views < 10_000:
        return min(10, points)
    return points


def _score_virality_retention(views: int | None, share_count: int | None, favorite_count: int | None) -> int:
    if views is None or views <= 0:
        return 0
    viral_rate = ((share_count or 0) * 1.5 + (favorite_count or 0) * 2.0) / views
    if viral_rate >= 0.03:
        return 20
    if viral_rate >= 0.015:
        return 15
    if viral_rate >= 0.005:
        return 10
    return 5


def _score_outlier_bonus(views: int | None, follower_count: int | None) -> int:
    if views is None or views <= 0:
        return 0
    if follower_count is None or follower_count <= 0:
        return 0
    return 15 if views / follower_count > 10 else 0


def _score_duration_fit(duration: float | None) -> int:
    if duration is None:
        return 0
    if 12 <= duration <= 75:
        return 10
    if 6 <= duration <= 120:
        return 7
    return 3


def _score_recency(posted_at: datetime | None) -> int:
    if posted_at is None:
        return 0
    age_ms = max(0, (datetime.now(UTC) - posted_at).total_seconds() * 1000)
    age_hours = age_ms / 3_600_000
    if age_hours <= 48:
        return 20
    age_days = age_hours / 24
    if age_days <= 7:
        return 15
    if age_days <= 30:
        return 10
    return 5


def _score_penalty(
    item: CapturedItem,
    has_thumbnail: bool,
    has_duration: bool,
    has_posted: bool,
    has_views: bool,
    has_any_metric: bool,
    *,
    metadata: dict[str, Any] | None = None,
) -> int:
    penalty = 0
    if not has_thumbnail:
        penalty -= 8
    if not has_duration:
        penalty -= 5
    if not has_posted:
        penalty -= 4
    if not has_any_metric:
        penalty -= 10
    item_status = getattr(item, "status", None)
    if item_status in {CapturedItemStatus.DUPLICATE, CapturedItemStatus.FAILED} or getattr(item, "duplicate_of_item_id", None) or getattr(item, "existing_source_video_id", None):
        penalty -= 20
    metadata = metadata or {}
    if metadata.get("metadata_status") == "failed":
        penalty -= 20
    if item_status in {CapturedItemStatus.RAW, CapturedItemStatus.NEEDS_ENRICHMENT, CapturedItemStatus.PREVIEW_MISSING}:
        penalty -= 8
    if not has_views:
        penalty -= 5
    return max(-30, penalty)


def _score_reasons(
    *,
    label: str,
    views: int | None,
    like_count: int | None,
    comment_count: int | None,
    share_count: int | None,
    favorite_count: int | None,
    follower_count: int | None,
    duration_seconds: float | None,
    missing: list[str],
    has_thumbnail: bool,
    has_posted: bool,
    has_views: bool,
    outlier_bonus: int,
) -> list[str]:
    reasons: list[str] = []
    engagement_rate = ((like_count or 0) + (comment_count or 0)) / views if views and views > 0 else None
    if label == "Needs metadata":
        reasons.append("Needs metadata")
    if views is not None and 100_000 <= views <= 3_000_000:
        reasons.append("Sweet-spot view range")
    if views is not None and views > 10_000_000:
        reasons.append("Saturated mega-views")
    if engagement_rate is not None and engagement_rate >= 0.03 and (views or 0) >= 10_000:
        reasons.append("Good engagement rate")
    if share_count is not None and favorite_count is not None and views and views > 0:
        viral_rate = ((share_count or 0) * 1.5 + (favorite_count or 0) * 2.0) / views
        if viral_rate >= 0.015:
            reasons.append("Strong share/save signal")
    if duration_seconds is not None and 12 <= duration_seconds <= 75:
        reasons.append("Duration fits review range")
    if outlier_bonus > 0:
        reasons.append("Outlier reach vs followers")
    if not has_posted or "posted" in missing:
        reasons.append("Missing posted date")
    if not has_thumbnail or "thumbnail" in missing:
        reasons.append("Missing thumbnail")
    if not has_views or "views" in missing:
        reasons.append("Needs estimated views")
    if follower_count is None and views is not None and views >= 100_000:
        reasons.append("Follower count unavailable")
    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return deduped[:4]


def _label_for_score(score: int, missing: list[str]) -> tuple[str, str]:
    key_missing = any(field in {"thumbnail", "duration", "posted", "views"} for field in missing)
    if score == 0 or (key_missing and score < 40) or sum(1 for field in missing if field in {"thumbnail", "duration", "posted", "views"}) >= 3:
        return "Needs metadata", "needs_metadata"
    if score >= 80:
        return "Excellent", "excellent"
    if score >= 60:
        return "Good", "good"
    if score >= 40:
        return "Average", "average"
    return "Low", "low"


def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _payload_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _capture_item_title_from_payloads(*, caption: str | None, metadata: dict[str, Any], raw: dict[str, Any], aweme_id: Any) -> str | None:
    blocked = {value for value in (_string_or_none(aweme_id),) if value}
    metadata_evidence = _payload_record(metadata.get("profile_card_evidence"))
    metadata_dom = _payload_record(metadata.get("raw_dom_detail_metrics"))
    raw_evidence = _payload_record(raw.get("profile_card_evidence"))
    raw_dom = _payload_record(raw.get("raw_dom_detail_metrics"))
    for value in (
        caption,
        raw.get("title"),
        raw.get("desc"),
        metadata.get("title"),
        metadata_evidence.get("title"),
        metadata_evidence.get("caption"),
        metadata_evidence.get("desc"),
        metadata_evidence.get("description"),
        metadata_dom.get("title"),
        raw_evidence.get("title"),
        raw_evidence.get("caption"),
        raw_evidence.get("desc"),
        raw_evidence.get("description"),
        raw_dom.get("title"),
    ):
        title = _string_or_none(value)
        if title and title not in blocked:
            return title
    return None


def _first_present(*values: Any) -> Any:
    for value in values:
        if value is None or value == "":
            continue
        return value
    return None


def _string_list_or_none(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    values = [entry.strip() for entry in value if isinstance(entry, str) and entry.strip()]
    return values or None


def _derive_preview_status(*, thumbnail_url: str | None, requested_status: Any = None) -> str:
    if thumbnail_url and _is_allowed_thumbnail_candidate(str(thumbnail_url), preferred_key=True):
        return "ready"
    return "missing"


def _derive_source_link_status(*, source_url: str | None, share_url: str | None, requested_status: Any = None) -> str:
    if requested_status == "captured" and (source_url or share_url):
        return "captured"
    if source_url or share_url:
        return "captured"
    return "missing"


def _derive_media_asset_status(*, requested_status: Any = None, legacy_media_status: Any = None) -> str:
    if requested_status == "failed":
        return "failed"
    return "not_generated"


def _legacy_media_status(*, source_link_status: str, media_asset_status: str) -> str:
    if media_asset_status == "ready":
        return "ready"
    if source_link_status == "captured":
        return "source_link_captured"
    return "missing"


def _status_counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not isinstance(value, str) or not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


_THUMBNAIL_PRIORITY_KEYS = (
    "thumbnail_url",
    "poster_url",
    "poster",
    "cover_url",
    "cover",
    "origin_cover",
    "dynamic_cover",
    "animated_cover",
    "thumb_url",
    "thumbnail",
    "image_url",
    "image",
    "url_list",
)

_THUMBNAIL_HINT_KEYS = frozenset(_THUMBNAIL_PRIORITY_KEYS)
_IMAGE_HOST_MARKERS = ("douyinpic.com", "byteimg.com", "douyinstatic.com")


def _thumbnail_url_from_payload(payload: dict[str, Any]) -> str | None:
    for key in _THUMBNAIL_PRIORITY_KEYS:
        if key in payload:
            found = _find_image_like_url(payload[key], preferred_key=True)
            if found:
                return _promote_douyin_storage_thumbnail_url(found)
    found = _find_image_like_url(payload, preferred_key=False)
    return _promote_douyin_storage_thumbnail_url(found) if found else None


def _find_image_like_url(value: Any, *, preferred_key: bool = False) -> str | None:
    if isinstance(value, str):
        candidate = value.strip()
        if candidate and (preferred_key or _is_image_like_url(candidate)) and _is_allowed_thumbnail_candidate(candidate, preferred_key=preferred_key):
            return candidate
        return None
    if isinstance(value, list):
        for entry in value:
            found = _find_image_like_url(entry, preferred_key=preferred_key)
            if found:
                return found
        return None
    if isinstance(value, dict):
        for key in _THUMBNAIL_PRIORITY_KEYS:
            if key in value:
                found = _find_image_like_url(value[key], preferred_key=True)
                if found:
                    return found
        for key, nested in value.items():
            key_lower = str(key).lower()
            if key_lower in _THUMBNAIL_HINT_KEYS or "cover" in key_lower or "poster" in key_lower or "thumb" in key_lower or "image" in key_lower:
                found = _find_image_like_url(nested, preferred_key=True)
                if found:
                    return found
        for nested in value.values():
            found = _find_image_like_url(nested, preferred_key=False)
            if found:
                return found
    return None


def _is_allowed_thumbnail_candidate(value: str, *, preferred_key: bool) -> bool:
    lower = value.lower()
    if any(marker in lower for marker in ("getapp", "get-app", "download", "avatar", "logo", "icon", "sprite", "favicon", "qrcode", "qr_code")):
        return False
    if _is_image_like_url(value):
        return True
    if "/tos-" in lower and ("douyin.com" in lower or "iesdouyin.com" in lower):
        return True
    if not preferred_key:
        return False
    return lower.startswith(("http://", "https://")) and any(marker in lower for marker in _IMAGE_HOST_MARKERS)


def _promote_douyin_storage_thumbnail_url(value: str | None) -> str | None:
    if not value or not isinstance(value, str):
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    lower = trimmed.lower()
    if "/tos-" not in lower:
        return trimmed
    try:
        parsed = urlparse(trimmed if "://" in trimmed else f"https:{trimmed}")
        path = parsed.path or ""
        host = (parsed.hostname or "").lower()
        if any(marker in lower for marker in _IMAGE_HOST_MARKERS):
            return trimmed
        if host.endswith("douyin.com") or host.endswith("iesdouyin.com"):
            return trimmed
        if not path.startswith("/"):
            path = f"/{path}"
        if not path.startswith("/tos-"):
            return trimmed
        if re.search(r"\.(jpe?g|png|webp|gif|avif)$", path, re.I):
            return f"https://p3-sign.douyinpic.com{path}{parsed.query and f'?{parsed.query}' or ''}"
        return trimmed
    except Exception:
        return trimmed


def _is_image_like_url(value: str) -> bool:
    lower = value.lower().split("?", 1)[0]
    return lower.startswith(("http://", "https://", "data:image/")) and (
        lower.startswith("data:image/") or lower.endswith((".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"))
    )


def _has_thumbnail_signature(value: str) -> bool:
    lower = value.lower()
    return "x-signature=" in lower or "x-expires=" in lower


def _collect_thumbnail_url_candidates(value: Any, *, out: list[str], seen: set[str]) -> None:
    if isinstance(value, str):
        trimmed = value.strip()
        if trimmed and trimmed not in seen and _is_allowed_thumbnail_candidate(trimmed, preferred_key=True):
            seen.add(trimmed)
            out.append(trimmed)
        return
    if isinstance(value, list):
        for entry in value:
            _collect_thumbnail_url_candidates(entry, out=out, seen=seen)
        return
    if isinstance(value, dict):
        for key in _THUMBNAIL_PRIORITY_KEYS:
            if key in value:
                _collect_thumbnail_url_candidates(value[key], out=out, seen=seen)
        for nested in value.values():
            if isinstance(nested, (dict, list, str)):
                _collect_thumbnail_url_candidates(nested, out=out, seen=seen)


def _thumbnail_fetch_candidates(item: CapturedItem) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for candidate in (
        item.thumbnail_url,
        item.preview_url,
    ):
        if not candidate or not isinstance(candidate, str):
            continue
        trimmed = candidate.strip()
        if not trimmed or trimmed in seen:
            continue
        seen.add(trimmed)
        ordered.append(trimmed)
    payload_candidates: list[str] = []
    payload_seen: set[str] = set()
    for payload in (item.raw_payload_json or {}, item.metadata_json or {}):
        _collect_thumbnail_url_candidates(payload, out=payload_candidates, seen=payload_seen)
    promoted_payload = [_promote_douyin_storage_thumbnail_url(c) or c for c in payload_candidates]
    for candidate in promoted_payload:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        ordered.append(candidate)
    ordered.sort(key=lambda url: (0 if _has_thumbnail_signature(url) else 1 if "douyinpic.com" in url.lower() or "byteimg.com" in url.lower() else 2))
    return ordered


def _fetch_remote_image(url: str) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "Referer": "https://www.douyin.com/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=12) as response:  # noqa: S310 — controlled outbound fetch for operator preview
        content_type = response.headers.get_content_type() if hasattr(response.headers, "get_content_type") else response.headers.get("Content-Type", "image/jpeg")
        data = response.read()
        if not data:
            raise ValueError("empty_thumbnail_response")
        if not str(content_type).lower().startswith("image/"):
            raise ValueError(f"unexpected_content_type:{content_type}")
        return data, str(content_type)


def _video_id_from_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    parts = [part for part in parsed.path.split("/") if part]
    if "video" in parts:
        index = parts.index("video")
        if len(parts) > index + 1:
            return parts[index + 1]
    return None


def _dedupe_key(source_video_external_id: str | None, source_url: str | None) -> str | None:
    if source_video_external_id:
        return f"douyin:video:{source_video_external_id}"
    if source_url:
        return f"douyin:url:{source_url}"
    return None


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None



def _float_or_none(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _engagement_rate_or_none(
    value: Any,
    *,
    view_count: int | None,
    like_count: int | None,
    comment_count: int | None,
    share_count: int | None,
) -> float | None:
    parsed = _float_or_none(value)
    if parsed is not None and parsed >= 0:
        return parsed
    if view_count is None or view_count <= 0:
        return None
    likes = like_count or 0
    comments = comment_count or 0
    shares = share_count or 0
    numerator = likes + comments + shares
    if numerator < 0:
        return None
    return float(numerator) / float(view_count)


def _datetime_or_none(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            return None
    return None


def _runtime_error_from_exception(exc: Exception, *, stage: str, diagnostics_id: str | None = None) -> CaptureInboxRuntimeError:
    message = str(exc) or exc.__class__.__name__
    lowered = message.lower()
    original = getattr(exc, "orig", None)
    original_message = str(original).lower() if original is not None else ""
    combined = f"{lowered} {original_message}"
    if "capture_sessions" in combined or "captured_items" in combined:
        if any(marker in combined for marker in ["does not exist", "no such table", "undefinedtable", "unknown table"]):
            return CaptureInboxRuntimeError(
                "schema_missing",
                "Capture Inbox database schema is missing required tables. Apply migrations and restart the backend on the extension API port.",
                stage="capture_inbox_schema_readiness" if stage == "capture_inbox_schema_readiness" else stage,
                diagnostics_id=diagnostics_id,
            )
        if any(marker in combined for marker in ["undefinedcolumn", "no such column", "unknown column", "column", "missing"]):
            return CaptureInboxRuntimeError(
                "migration_mismatch",
                "Capture Inbox database schema does not match the running backend model. Apply the latest migrations and restart the backend.",
                stage="capture_inbox_schema_readiness" if stage == "capture_inbox_schema_readiness" else stage,
                diagnostics_id=diagnostics_id,
            )
    code = "capture_session_persist_failed" if stage in {"capture_session_persist", "capture_session_reconcile"} else "captured_item_persist_failed"
    operator_message = (
        "Capture Inbox could not persist the Capture Session. Check database connectivity, apply migrations, and restart the backend."
        if code == "capture_session_persist_failed"
        else "Capture Inbox could not persist one or more Captured Items. Check database connectivity and migration state."
    )
    return CaptureInboxRuntimeError(code, operator_message, stage=stage, diagnostics_id=diagnostics_id)


def _failure_summary(*, stage: str, item_index: int | None, code: str, message: str) -> CaptureInboxItemFailureSummary:
    return CaptureInboxItemFailureSummary(stage=stage, item_index=item_index, code=code, message=message[:500])


def _suspicious_duplicate_payload_mapping_count(items: list[CapturedItem]) -> int:
    signatures: dict[str, set[str]] = {}
    for item in items:
        if not item.source_video_external_id:
            continue
        metadata = item.metadata_json or {}
        if not metadata.get("network_source"):
            continue
        signature = "|".join(
            str(metadata.get(key) or item.thumbnail_url or "")
            if key == "thumbnail_url"
            else str(metadata.get(key) or "")
            for key in ("thumbnail_url", "posted_at", "view_count", "like_count", "comment_count")
        )
        if not signature.replace("|", ""):
            continue
        signatures.setdefault(signature, set()).add(item.source_video_external_id)
    return sum(1 for source_ids in signatures.values() if len(source_ids) > 1)



def _targeted_aweme_one_shot_summary_path() -> Path:
    return (Path(__file__).resolve().parents[2] / "tmp" / "targeted_aweme_one_shot_summary.json").resolve()


def _write_targeted_aweme_one_shot_summary_file(*, capture_session_id: str, capture_id: str | None, summaries_by_aweme: dict[str, dict[str, Any]]) -> None:
    output_path = _targeted_aweme_one_shot_summary_path()
    parent_path = output_path.parent
    parent_existed_before = parent_path.exists()
    aweme_ids = sorted(summaries_by_aweme.keys())
    logger.info(
        "targeted_aweme_one_shot_write_attempt",
        extra={
            "absolute_path": str(output_path),
            "aweme_ids": aweme_ids,
            "parent_dir_existed_before": parent_existed_before,
            "capture_session_id": capture_session_id,
            "capture_id": capture_id,
        },
    )
    try:
        parent_path.mkdir(parents=True, exist_ok=True)
        payload = {
            "generated_at": datetime.now(UTC).isoformat(),
            "capture_session_id": capture_session_id,
            "capture_id": capture_id,
            "items": [summaries_by_aweme[aweme_id] for aweme_id in aweme_ids],
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(
            "targeted_aweme_one_shot_write_success",
            extra={
                "absolute_path": str(output_path),
                "item_count": len(payload["items"]),
                "capture_session_id": capture_session_id,
                "capture_id": capture_id,
            },
        )
    except Exception as exc:
        logger.exception(
            "targeted_aweme_one_shot_write_error",
            extra={
                "absolute_path": str(output_path),
                "error_message": str(exc),
                "capture_session_id": capture_session_id,
                "capture_id": capture_id,
            },
        )


def _warning_codes_for_stage(session: CaptureSession, failures: list[CaptureInboxItemFailureSummary], *, suspicious_duplicate_payload_mapping_count: int = 0) -> list[str]:
    codes: list[str] = []
    if failures:
        codes.append("partial_item_failures")
    if session.duplicate_item_count:
        codes.append("duplicate_items_detected")
    if suspicious_duplicate_payload_mapping_count:
        codes.append("suspicious_duplicate_payload_mapping")
    if session.ready_item_count == 0 and session.captured_item_count > 0:
        codes.append("no_ready_items")
    if session.captured_item_count == 0:
        codes.append("no_items_staged")
    return codes
