from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.enums import CapturedItemStatus, SourcePlatformEnum
from src.models.capture_inbox import CaptureSession, CapturedItem
from src.services.capture_metadata_normalizer import CaptureMetadataNormalizeInput, CaptureMetadataNormalizer
from src.services.douyin_account_service import DouyinAccountError, DouyinAccountService, DouyinFetchPreflightResult
from src.services.douyin_browser_context_registry import douyin_browser_context_registry

logger = logging.getLogger(__name__)

_DETAIL_SECRET_MARKERS = ("cookie", "token", "authorization", "header", "credential", "mstoken", "csrf")
_DETAIL_USEFUL_KEYS = {
    "aweme_id",
    "create_time",
    "statistics",
    "video",
    "desc",
    "author",
    "share_info",
    "text_extra",
    "music",
}
_JSON_MARKERS = (
    "window.__INIT_PROPS__",
    "window.__INITIAL_STATE__",
    "window.__UNIVERSAL_DATA_FOR_REHYDRATION__",
    "__UNIVERSAL_DATA_FOR_REHYDRATION__",
    "SIGI_STATE",
    "RENDER_DATA",
)
_DETAIL_CAPTCHA_MARKERS = (
    "captcha",
    "verify",
    "verification",
    "security check",
    "challenge",
    "验证码",
    "安全验证",
    "请完成验证",
    "滑块",
    "抖音安全中心",
)
_DETAIL_BLOCK_MARKERS = (
    "access denied",
    "blocked",
    "forbidden",
    "request rejected",
    "security center",
)


class CaptureInboxMetadataHydrationError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


@dataclass(frozen=True)
class CaptureInboxMetadataHydrationItemResult:
    item_id: UUID
    aweme_id: str | None
    detail_url: str | None
    outcome: str
    message: str
    duration_seconds: float | None = None
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None


@dataclass(frozen=True)
class CaptureInboxMetadataHydrationResult:
    capture_session_id: UUID
    selected_account_id: UUID
    selected_fetch_path: str
    total_items_considered: int
    hydrated_count: int
    skipped_count: int
    failed_count: int
    detail_hydrate_attempted_count: int
    detail_hydrate_success_count: int
    detail_hydrate_failed_count: int
    detail_hydrate_timeout_count: int
    captcha_required_count: int
    detail_page_blocked_count: int
    raw_detail_aweme_attached_count: int
    concurrency_limit_requested: int
    concurrency_limit_effective: int
    timeout_seconds: float
    next_operator_action: str | None
    item_results: list[CaptureInboxMetadataHydrationItemResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_session_id": str(self.capture_session_id),
            "selected_account_id": str(self.selected_account_id),
            "selected_fetch_path": self.selected_fetch_path,
            "total_items_considered": self.total_items_considered,
            "hydrated_count": self.hydrated_count,
            "skipped_count": self.skipped_count,
            "failed_count": self.failed_count,
            "detail_hydrate_attempted_count": self.detail_hydrate_attempted_count,
            "detail_hydrate_success_count": self.detail_hydrate_success_count,
            "detail_hydrate_failed_count": self.detail_hydrate_failed_count,
            "detail_hydrate_timeout_count": self.detail_hydrate_timeout_count,
            "captcha_required_count": self.captcha_required_count,
            "detail_page_blocked_count": self.detail_page_blocked_count,
            "raw_detail_aweme_attached_count": self.raw_detail_aweme_attached_count,
            "concurrency_limit_requested": self.concurrency_limit_requested,
            "concurrency_limit_effective": self.concurrency_limit_effective,
            "timeout_seconds": self.timeout_seconds,
            "next_operator_action": self.next_operator_action,
            "item_results": [
                {
                    "item_id": str(item.item_id),
                    "aweme_id": item.aweme_id,
                    "detail_url": item.detail_url,
                    "outcome": item.outcome,
                    "message": item.message,
                    "duration_seconds": item.duration_seconds,
                    "view_count": item.view_count,
                    "like_count": item.like_count,
                    "comment_count": item.comment_count,
                    "share_count": item.share_count,
                }
                for item in self.item_results
            ],
        }


class CaptureInboxMetadataHydrationService:
    def __init__(self, db: Session):
        self.db = db
        self._normalizer = CaptureMetadataNormalizer()

    def latest_capture_session_id(self) -> UUID | None:
        stmt = (
            select(CaptureSession.id)
            .where(CaptureSession.source_platform == SourcePlatformEnum.DOUYIN)
            .order_by(CaptureSession.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(stmt)

    def hydrate_latest_capture_session_metadata(
        self,
        *,
        account_connection_id: UUID | None = None,
        limit: int | None = None,
        timeout_seconds: float = 10.0,
        concurrency_limit: int = 2,
        force: bool = False,
    ) -> CaptureInboxMetadataHydrationResult:
        session_id = self.latest_capture_session_id()
        if session_id is None:
            raise CaptureInboxMetadataHydrationError(
                "capture_session_not_found",
                "No Douyin capture session was found for metadata hydration.",
            )
        return self.hydrate_capture_session_metadata(
            session_id,
            account_connection_id=account_connection_id,
            limit=limit,
            timeout_seconds=timeout_seconds,
            concurrency_limit=concurrency_limit,
            force=force,
        )

    def hydrate_capture_session_metadata(
        self,
        capture_session_id: UUID,
        *,
        account_connection_id: UUID | None = None,
        limit: int | None = None,
        timeout_seconds: float = 10.0,
        concurrency_limit: int = 2,
        force: bool = False,
    ) -> CaptureInboxMetadataHydrationResult:
        session = self._get_capture_session(capture_session_id)
        account, preflight = self._resolve_browser_backed_account(
            workspace_id=session.workspace_id,
            requested_account_id=account_connection_id,
        )
        if preflight.preflight_result != "passed" or preflight.selected_fetch_path != "browser_profile":
            raise CaptureInboxMetadataHydrationError(
                preflight.preflight_failure_code or "browser_profile_not_ready",
                preflight.preflight_failure_message or "No browser-backed Douyin account is ready for metadata hydration.",
            )

        candidates = [item for item in session.items if self._needs_hydration(item, force=force)]
        if limit is not None:
            candidates = candidates[: max(0, int(limit))]
        self._ensure_browser_context_for_hydration(
            account=account,
            total_items_considered=len(candidates),
        )
        requested_concurrency = max(1, int(concurrency_limit))
        effective_concurrency = 1
        item_results: list[CaptureInboxMetadataHydrationItemResult] = []
        attempted_count = 0
        success_count = 0
        failed_count = 0
        timeout_count = 0
        skipped_count = 0
        attached_count = 0
        captcha_required_count = 0
        detail_page_blocked_count = 0
        stop_reason_code: str | None = None
        stop_reason_message: str | None = None

        for item in candidates:
            attempted_count += 1
            result = self._hydrate_item(
                item,
                account_id=account.id,
                timeout_seconds=timeout_seconds,
            )
            item_results.append(result)
            if result.outcome == "hydrated":
                success_count += 1
                attached_count += 1
            elif result.outcome == "timeout":
                failed_count += 1
                timeout_count += 1
            elif result.outcome == "skipped":
                skipped_count += 1
            else:
                failed_count += 1
                if result.outcome == "captcha_required":
                    captcha_required_count += 1
                    stop_reason_code = "captcha_required"
                    stop_reason_message = "Douyin requires manual verification in the browser profile."
                    break
                if result.outcome == "detail_page_blocked":
                    detail_page_blocked_count += 1
                    stop_reason_code = "detail_page_blocked"
                    stop_reason_message = "Douyin blocked the detail page before metadata hydration could continue."
                    break

        session_metadata = dict(getattr(session, "metadata_json", None) or {})
        next_operator_action = None
        if stop_reason_code in {"captcha_required", "detail_page_blocked"}:
            next_operator_action = "open_browser_profile_complete_verification_then_rerun_hydration"
        session_metadata["last_metadata_hydration_run"] = {
            "capture_session_id": str(session.id),
            "selected_account_id": str(account.id),
            "selected_fetch_path": preflight.selected_fetch_path,
            "ran_at": datetime.now(UTC).isoformat(),
            "detail_hydrate_attempted_count": attempted_count,
            "detail_hydrate_success_count": success_count,
            "detail_hydrate_failed_count": failed_count,
            "detail_hydrate_timeout_count": timeout_count,
            "captcha_required_count": captcha_required_count,
            "detail_page_blocked_count": detail_page_blocked_count,
            "raw_detail_aweme_attached_count": attached_count,
            "concurrency_limit_requested": requested_concurrency,
            "concurrency_limit_effective": effective_concurrency,
            "timeout_seconds": timeout_seconds,
            "next_operator_action": next_operator_action,
            "stop_reason_code": stop_reason_code,
            "stop_reason_message": stop_reason_message,
        }
        session.metadata_json = session_metadata
        self.db.commit()

        if stop_reason_code is not None:
            raise CaptureInboxMetadataHydrationError(
                stop_reason_code,
                stop_reason_message or "Douyin requires manual verification in the browser profile.",
                details={
                    "capture_session_id": str(session.id),
                    "account_id": str(account.id),
                    "selected_fetch_path": preflight.selected_fetch_path or "browser_profile",
                    "hydrated_count": success_count,
                    "skipped_count": skipped_count,
                    "failed_count": failed_count,
                    "captcha_required_count": captcha_required_count,
                    "detail_page_blocked_count": detail_page_blocked_count,
                    "next_operator_action": next_operator_action,
                },
            )

        return CaptureInboxMetadataHydrationResult(
            capture_session_id=session.id,
            selected_account_id=account.id,
            selected_fetch_path=preflight.selected_fetch_path or "browser_profile",
            total_items_considered=len(candidates),
            hydrated_count=success_count,
            skipped_count=skipped_count,
            failed_count=failed_count,
            detail_hydrate_attempted_count=attempted_count,
            detail_hydrate_success_count=success_count,
            detail_hydrate_failed_count=failed_count,
            detail_hydrate_timeout_count=timeout_count,
            captcha_required_count=captcha_required_count,
            detail_page_blocked_count=detail_page_blocked_count,
            raw_detail_aweme_attached_count=attached_count,
            concurrency_limit_requested=requested_concurrency,
            concurrency_limit_effective=effective_concurrency,
            timeout_seconds=timeout_seconds,
            next_operator_action=next_operator_action,
            item_results=item_results,
        )

    def _get_capture_session(self, capture_session_id: UUID) -> CaptureSession:
        session = self.db.scalar(
            select(CaptureSession)
            .options(selectinload(CaptureSession.items))
            .where(CaptureSession.id == capture_session_id)
        )
        if session is None:
            raise CaptureInboxMetadataHydrationError(
                "capture_session_not_found",
                "Capture session was not found for metadata hydration.",
            )
        return session

    def _resolve_browser_backed_account(
        self,
        *,
        workspace_id: UUID,
        requested_account_id: UUID | None,
    ) -> tuple[Any, DouyinFetchPreflightResult]:
        account_service = DouyinAccountService(self.db)
        if requested_account_id is not None:
            account = account_service.get_account(requested_account_id)
            preflight = account_service.preflight_fetch_readiness(account.id)
            return account, preflight

        accounts = account_service.list_accounts(workspace_id=workspace_id)
        default_account = account_service.default_account(workspace_id=workspace_id)
        ordered: list[Any] = []
        if default_account is not None:
            ordered.append(default_account)
        ordered.extend(account for account in accounts if default_account is None or account.id != default_account.id)

        first_failure: CaptureInboxMetadataHydrationError | None = None
        for account in ordered:
            metadata = dict(getattr(account, "metadata_json", None) or {})
            if not self._has_saved_browser_profile(metadata):
                continue
            preflight = account_service.preflight_fetch_readiness(account.id)
            if preflight.preflight_result == "passed" and preflight.selected_fetch_path == "browser_profile":
                return account, preflight
            if first_failure is None:
                first_failure = CaptureInboxMetadataHydrationError(
                    preflight.preflight_failure_code or "browser_profile_not_ready",
                    preflight.preflight_failure_message or "Browser-backed Douyin account is not fetch-ready for metadata hydration.",
                )
        if first_failure is not None:
            raise first_failure
        raise CaptureInboxMetadataHydrationError(
            "browser_profile_required",
            "No browser-profile-backed Douyin account is available for metadata hydration.",
        )

    def _ensure_browser_context_for_hydration(
        self,
        *,
        account: Any,
        total_items_considered: int,
    ) -> None:
        account_service = DouyinAccountService(self.db)
        summary = douyin_browser_context_registry.summary_for_account(account.id)
        if summary.status != "active":
            reopened = account_service._ensure_persistent_profile_context(account, purpose="fetch", force=True)
            self.db.commit()
            summary = douyin_browser_context_registry.summary_for_account(account.id)
            if summary.status != "active":
                code, message = self._browser_context_failure_from_summary(reopened or summary)
                raise CaptureInboxMetadataHydrationError(
                    code,
                    message,
                    details={
                        "selected_account_id": str(account.id),
                        "selected_fetch_path": "browser_profile",
                        "total_items_considered": total_items_considered,
                        "detail_hydrate_attempted_count": 0,
                        "recommended_command": f"python scripts/douyin_account_readiness.py --account-id {account.id} --open-profile --timeout-seconds 300",
                    },
                )

        validation = douyin_browser_context_registry.validate_account_context(
            account.id,
            validation_url="https://www.douyin.com/",
        )
        if validation.status == "login_required":
            raise CaptureInboxMetadataHydrationError(
                "manual_login_required",
                validation.reason or "Douyin login is required in the saved browser profile.",
                details={
                    "account_id": str(account.id),
                    "selected_fetch_path": "browser_profile",
                    "total_items_considered": total_items_considered,
                    "detail_hydrate_attempted_count": 0,
                },
            )
        if validation.status == "blocked":
            raise CaptureInboxMetadataHydrationError(
                "captcha_required",
                validation.reason or "Douyin requires manual verification in the browser profile.",
                details={
                    "account_id": str(account.id),
                    "selected_fetch_path": "browser_profile",
                    "total_items_considered": total_items_considered,
                    "detail_hydrate_attempted_count": 0,
                    "captcha_required_count": 0,
                    "detail_page_blocked_count": 0,
                },
            )
        if validation.status in {"none", "stale", "closed", "invalid"} and validation.runtime_attach_status == "runtime_missing_reopen_required":
            code, message = self._browser_context_failure_from_validation(validation)
            raise CaptureInboxMetadataHydrationError(
                code,
                message,
                details={
                    "account_id": str(account.id),
                    "selected_fetch_path": "browser_profile",
                    "total_items_considered": total_items_considered,
                    "detail_hydrate_attempted_count": 0,
                    "recommended_command": f"python scripts/douyin_account_readiness.py --account-id {account.id} --open-profile --timeout-seconds 300",
                },
            )

    def _browser_context_failure_from_summary(self, summary: Any) -> tuple[str, str]:
        reason = str(getattr(summary, "reason", "") or "")
        lowered = reason.lower()
        if "profile_locked_by_existing_process" in lowered or "singletonlock" in lowered or "processsingleton" in lowered:
            return "browser_profile_locked", reason or "Saved browser profile is locked by another browser process."
        if "timeout" in lowered:
            return "browser_launch_timeout", reason or "Saved browser profile launch timed out."
        if reason:
            return "profile_open_failed", reason
        return "browser_context_unavailable", "No live browser context is available for the saved Douyin browser profile."

    def _browser_context_failure_from_validation(self, validation: Any) -> tuple[str, str]:
        reason = str(getattr(validation, "reason", "") or "")
        lowered = reason.lower()
        if "profile_locked_by_existing_process" in lowered or "singletonlock" in lowered or "processsingleton" in lowered:
            return "browser_profile_locked", reason or "Saved browser profile is locked by another browser process."
        if reason == "no_live_browser_context":
            return "browser_context_unavailable", "Saved browser profile could not provide a live browser context for hydration."
        return "browser_context_unavailable", reason or "Saved browser profile could not provide a live browser context for hydration."

    def _needs_hydration(self, item: CapturedItem, *, force: bool) -> bool:
        if force:
            return True
        if item.status in {CapturedItemStatus.DUPLICATE, CapturedItemStatus.EXCLUDED, CapturedItemStatus.PROMOTED}:
            return False
        metadata = dict(getattr(item, "metadata_json", None) or {})
        performance_status = str(metadata.get("performance_status") or "").lower()
        processing_fit_status = str(metadata.get("processing_fit_status") or "").lower()
        if performance_status in {"missing", "pending", "failed"}:
            return True
        if processing_fit_status in {"missing", "pending", "failed"}:
            return True
        if item.duration_seconds is None:
            return True
        if metadata.get("view_count") is None and metadata.get("like_count") is None:
            return True
        return False

    def _hydrate_item(
        self,
        item: CapturedItem,
        *,
        account_id: UUID,
        timeout_seconds: float,
    ) -> CaptureInboxMetadataHydrationItemResult:
        aweme_id = _normalize_aweme_id(item.source_video_external_id)
        detail_url = self._detail_url_for_item(item, aweme_id)
        if aweme_id is None:
            self._mark_item_hydration_failure(
                item,
                message="No aweme_id was available for metadata hydration.",
                code="aweme_id_missing",
                detail_url=detail_url,
            )
            return CaptureInboxMetadataHydrationItemResult(item.id, None, detail_url, "failed", "aweme_id_missing")
        try:
            fetch_result = douyin_browser_context_registry.fetch_detail_page(
                account_id,
                detail_url=detail_url,
                timeout_ms=max(1_000, int(float(timeout_seconds) * 1000)),
                settle_seconds=1,
                scroll_passes=0,
            )
        except Exception as exc:  # noqa: BLE001
            self._mark_item_hydration_failure(
                item,
                message=f"browser_detail_fetch_exception:{exc.__class__.__name__}",
                code="browser_detail_fetch_exception",
                detail_url=detail_url,
            )
            return CaptureInboxMetadataHydrationItemResult(item.id, aweme_id, detail_url, "failed", f"browser_detail_fetch_exception:{exc.__class__.__name__}")

        if not fetch_result.available:
            message = fetch_result.reason or fetch_result.status or "browser_detail_unavailable"
            self._mark_item_hydration_failure(item, message=message, code="detail_fetch_unavailable", detail_url=detail_url)
            outcome = "timeout" if "timeout" in message.lower() else "failed"
            return CaptureInboxMetadataHydrationItemResult(item.id, aweme_id, detail_url, outcome, message)

        access_issue = classify_detail_page_access(
            page_url=getattr(fetch_result, "page_url", None),
            title=getattr(fetch_result, "title", None),
            html=getattr(fetch_result, "html", None),
            response_documents=getattr(fetch_result, "response_documents", None),
        )
        if access_issue is not None:
            issue_code, issue_message = access_issue
            self._mark_item_hydration_failure(
                item,
                message=issue_message,
                code=issue_code,
                detail_url=getattr(fetch_result, "page_url", None) or detail_url,
            )
            return CaptureInboxMetadataHydrationItemResult(item.id, aweme_id, detail_url, issue_code, issue_message)

        raw_detail_aweme = extract_detail_aweme_from_browser_artifacts(
            target_aweme_id=aweme_id,
            html=fetch_result.html,
            response_documents=fetch_result.response_documents,
        )
        if raw_detail_aweme is None:
            self._mark_item_hydration_failure(item, message="detail_aweme_not_found", code="detail_aweme_not_found", detail_url=detail_url)
            return CaptureInboxMetadataHydrationItemResult(item.id, aweme_id, detail_url, "failed", "detail_aweme_not_found")

        metadata = dict(getattr(item, "metadata_json", None) or {})
        evidence_summary = dict(metadata.get("raw_evidence_summary") or {})
        metadata["raw_detail_aweme"] = raw_detail_aweme
        metadata["raw_evidence_summary"] = _merge_raw_evidence_summary(
            existing=evidence_summary,
            raw_detail_aweme=raw_detail_aweme,
            raw_dom_snapshot=metadata.get("raw_dom_snapshot"),
        )
        metadata["last_metadata_hydration_attempted_at"] = datetime.now(UTC).isoformat()
        metadata["metadata_hydration_attempt_count"] = int(metadata.get("metadata_hydration_attempt_count") or 0) + 1
        metadata["last_metadata_hydration_source"] = "backend_browser_detail_hydrate"
        metadata["last_metadata_hydration_result"] = "success"
        metadata.pop("last_metadata_hydration_error", None)

        normalized = self._normalizer.normalize(
            CaptureMetadataNormalizeInput(
                raw_network_aweme=metadata.get("raw_network_aweme") if isinstance(metadata.get("raw_network_aweme"), dict) else None,
                raw_detail_aweme=raw_detail_aweme,
                raw_dom_snapshot=metadata.get("raw_dom_snapshot") if isinstance(metadata.get("raw_dom_snapshot"), dict) else None,
                raw_evidence_summary=metadata["raw_evidence_summary"],
                existing_posted_at=item.posted_at,
                existing_posted_text=_string_or_none(metadata.get("posted_text")),
                existing_duration_seconds=item.duration_seconds,
                existing_duration_text=_string_or_none(metadata.get("duration_text")),
                existing_view_count=_int_or_none(metadata.get("view_count")),
                existing_like_count=_int_or_none(metadata.get("like_count")),
                existing_comment_count=_int_or_none(metadata.get("comment_count")),
                existing_share_count=_int_or_none(metadata.get("share_count")),
                existing_engagement_rate=_float_or_none(metadata.get("engagement_rate")),
            )
        )

        item.posted_at = normalized.posted_at
        item.duration_seconds = normalized.duration_seconds
        metadata.update(
            {
                "posted_at": normalized.posted_at.isoformat() if normalized.posted_at else None,
                "posted_text": normalized.posted_text,
                "duration_seconds": normalized.duration_seconds,
                "duration_text": normalized.duration_text,
                "view_count": normalized.view_count,
                "like_count": normalized.like_count,
                "comment_count": normalized.comment_count,
                "share_count": normalized.share_count,
                "engagement_rate": normalized.engagement_rate,
                "posted_source": normalized.posted_source,
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
                "hydration_detail_url": detail_url,
                "hydration_browser_execution_path": "browser_detail",
            }
        )
        item.metadata_json = metadata
        self.db.add(item)
        self.db.commit()
        return CaptureInboxMetadataHydrationItemResult(
            item_id=item.id,
            aweme_id=aweme_id,
            detail_url=detail_url,
            outcome="hydrated",
            message="detail_aweme_attached",
            duration_seconds=normalized.duration_seconds,
            view_count=normalized.view_count,
            like_count=normalized.like_count,
            comment_count=normalized.comment_count,
            share_count=normalized.share_count,
        )

    def _mark_item_hydration_failure(
        self,
        item: CapturedItem,
        *,
        message: str,
        code: str = "failed",
        detail_url: str | None = None,
    ) -> None:
        metadata = dict(getattr(item, "metadata_json", None) or {})
        attempted_at = datetime.now(UTC).isoformat()
        metadata["metadata_hydration_attempted_at"] = attempted_at
        metadata["last_metadata_hydration_attempted_at"] = attempted_at
        metadata["last_metadata_hydrated_at"] = attempted_at
        metadata["metadata_hydration_attempt_count"] = int(metadata.get("metadata_hydration_attempt_count") or 0) + 1
        metadata["last_metadata_hydration_source"] = "backend_browser_detail_hydrate"
        metadata["last_metadata_hydration_result"] = code
        metadata["last_metadata_hydration_error"] = message[:300]
        metadata["metadata_hydration_status"] = code
        metadata["metadata_hydration_error_code"] = code
        metadata["metadata_hydration_error_message"] = message[:300]
        if detail_url:
            metadata["hydration_detail_url"] = detail_url
        if code in {"captcha_required", "detail_page_blocked"}:
            metadata["performance_missing_reason"] = code
            metadata["processing_fit_missing_reason"] = code
            metadata["captcha_required_at"] = attempted_at
            metadata["captcha_required_url"] = detail_url
        item.metadata_json = metadata
        self.db.add(item)
        self.db.commit()

    def _detail_url_for_item(self, item: CapturedItem, aweme_id: str | None) -> str | None:
        if item.source_url and _looks_like_douyin_url(item.source_url):
            return item.source_url
        if aweme_id:
            return f"https://www.douyin.com/video/{aweme_id}"
        return None

    def _has_saved_browser_profile(self, metadata: dict[str, Any]) -> bool:
        browser_profile_id = metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None
        browser_profile_path = metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None
        return bool(browser_profile_id or browser_profile_path)


def extract_detail_aweme_from_browser_artifacts(
    *,
    target_aweme_id: str,
    html: str | None,
    response_documents: list[dict | list] | None,
) -> dict[str, Any] | None:
    target = _normalize_aweme_id(target_aweme_id)
    if target is None:
        return None
    documents: list[dict | list] = []
    documents.extend(_json_documents_from_html(html or ""))
    documents.extend(item for item in (response_documents or []) if isinstance(item, (dict, list)))

    best_candidate: dict[str, Any] | None = None
    best_score = -1
    for candidate in _walk_json(documents):
        if not isinstance(candidate, dict):
            continue
        if _normalize_aweme_id(candidate.get("aweme_id")) != target:
            continue
        score = _detail_candidate_score(candidate)
        if score > best_score:
            best_score = score
            best_candidate = candidate
    if best_candidate is None:
        return None
    return _sanitize_detail_aweme(best_candidate)


def classify_detail_page_access(
    *,
    page_url: str | None,
    title: str | None,
    html: str | None,
    response_documents: list[dict | list] | None,
) -> tuple[str, str] | None:
    fragments = [
        str(page_url or ""),
        str(title or ""),
        str(html or "")[:10_000],
    ]
    if response_documents:
        try:
            fragments.append(json.dumps(response_documents[:3], ensure_ascii=False)[:4_000])
        except Exception:
            pass
    combined = "\n".join(fragment.lower() for fragment in fragments if fragment)
    if any(marker in combined for marker in _DETAIL_CAPTCHA_MARKERS):
        return ("captcha_required", "detail_page_captcha")
    if any(marker in combined for marker in _DETAIL_BLOCK_MARKERS):
        return ("detail_page_blocked", "detail_page_blocked")
    return None


def _json_documents_from_html(html: str) -> list[dict | list]:
    documents: list[dict | list] = []
    script_pattern = re.compile(r"<script[^>]*>(?P<body>.*?)</script>", re.DOTALL | re.IGNORECASE)
    for match in script_pattern.finditer(html):
        body = match.group("body").strip()
        parsed = _parse_jsonish(body)
        if parsed is not None:
            documents.append(parsed)
        for marker in _JSON_MARKERS:
            documents.extend(_parse_json_after_marker(body, marker))
    for marker in _JSON_MARKERS:
        documents.extend(_parse_json_after_marker(html, marker))
    return documents


def _parse_jsonish(value: str) -> dict | list | None:
    if not value:
        return None
    for candidate in (value, unescape(value)):
        stripped = candidate.strip().rstrip(";")
        if not stripped or stripped[0] not in "[{":
            continue
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, (dict, list)):
            return parsed
    return None


def _parse_json_after_marker(value: str, marker: str) -> list[dict | list]:
    decoder = json.JSONDecoder()
    documents: list[dict | list] = []
    start = 0
    while True:
        marker_index = value.find(marker, start)
        if marker_index == -1:
            break
        equals_index = value.find("=", marker_index)
        if equals_index == -1:
            break
        json_start = equals_index + 1
        while json_start < len(value) and value[json_start].isspace():
            json_start += 1
        try:
            parsed, end = decoder.raw_decode(value[json_start:])
        except json.JSONDecodeError:
            start = marker_index + len(marker)
            continue
        if isinstance(parsed, (dict, list)):
            documents.append(parsed)
        start = json_start + end
    return documents


def _walk_json(value: object):
    yield value
    if isinstance(value, dict):
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _detail_candidate_score(candidate: dict[str, Any]) -> int:
    score = 0
    for key in ("create_time", "video", "statistics", "desc", "author", "share_info"):
        if key in candidate:
            score += 1
    return score


def _sanitize_detail_aweme(value: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key in _DETAIL_USEFUL_KEYS:
        if key not in value:
            continue
        sanitized_value = _sanitize_value(value[key], depth=0)
        if sanitized_value is not None:
            sanitized[key] = sanitized_value
    aweme_id = _normalize_aweme_id(value.get("aweme_id"))
    if aweme_id is not None:
        sanitized["aweme_id"] = aweme_id
    return sanitized


def _sanitize_value(value: Any, *, depth: int) -> Any:
    if depth > 5:
        return None
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, nested in list(value.items())[:20]:
            normalized_key = str(key)
            if any(marker in normalized_key.lower() for marker in _DETAIL_SECRET_MARKERS):
                continue
            sanitized_nested = _sanitize_value(nested, depth=depth + 1)
            if sanitized_nested is not None:
                sanitized[normalized_key] = sanitized_nested
        return sanitized or None
    if isinstance(value, list):
        sanitized_items = []
        for entry in value[:20]:
            sanitized_entry = _sanitize_value(entry, depth=depth + 1)
            if sanitized_entry is not None:
                sanitized_items.append(sanitized_entry)
        return sanitized_items
    if isinstance(value, str):
        return value[:500]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:500]


def _merge_raw_evidence_summary(
    *,
    existing: dict[str, Any],
    raw_detail_aweme: dict[str, Any],
    raw_dom_snapshot: Any,
) -> dict[str, Any]:
    merged = dict(existing)
    detail_keys = sorted(raw_detail_aweme.keys())
    evidence_sources = [source for source in merged.get("evidence_sources", []) if isinstance(source, str)]
    for source in ("detail_hydrate", "browser_detail"):
        if source not in evidence_sources:
            evidence_sources.append(source)
    merged.update(
        {
            "has_network_aweme": bool(merged.get("has_network_aweme") is True),
            "has_detail_aweme": True,
            "has_dom_snapshot": isinstance(raw_dom_snapshot, dict),
            "detail_keys": detail_keys,
            "evidence_sources": evidence_sources,
            "evidence_collection_version": "phase5d_browser_detail_hydrate",
        }
    )
    return merged


def _normalize_aweme_id(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _looks_like_douyin_url(value: str) -> bool:
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    return parsed.scheme in {"http", "https"} and (host == "www.douyin.com" or host.endswith(".douyin.com"))


def _string_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


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
