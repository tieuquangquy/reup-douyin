from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import logging
import re
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from src.adapters.douyin_live_fetch import extract_profile_payload_from_browser_artifacts
from src.adapters.errors import SourceAdapterError
from src.enums import CrawlSessionStatus, SourcePlatformEnum
from src.models.ingestion import CrawlSession, SourceProfile
from src.services.candidate_service import CandidateEvaluationService
from src.services.candidate_types import FilterConfig
from src.services.douyin_browser_context_registry import douyin_browser_context_registry
from src.services.douyin_account_service import DouyinAccountService
from src.services.source_ingest_service import SourceIngestError, SourceIngestService

logger = logging.getLogger(__name__)

DOUYIN_CURRENT_PAGE_TYPES = {
    "login_page",
    "challenge_page",
    "home_feed_page",
    "profile_page",
    "profile_feed_page",
    "video_detail_page",
    "unsupported_page",
    "unknown_page",
}


class DouyinCurrentPageCaptureError(ValueError):
    def __init__(self, code: str, message: str, *, stage: str = "current_page_capture", diagnostics_id: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.diagnostics_id = diagnostics_id or str(uuid4())


@dataclass(frozen=True)
class DouyinCurrentPageDetection:
    diagnostics_id: str
    account_connection_id: UUID
    detected_page_type: str
    supported_capture: bool
    recommended_action: str
    recommended_action_label: str
    operator_message: str
    page_url: str | None
    normalized_profile_url: str | None
    title: str | None
    video_link_count: int
    runtime_context_id: str | None
    runtime_attach_status: str | None
    page_recovery_status: str | None
    managed_runtime_status: str | None
    detected_at: datetime
    reason: str | None = None


@dataclass(frozen=True)
class DouyinCurrentPageCaptureSummary:
    success: bool
    diagnostics_id: str
    account_connection_id: UUID
    detected_page_type: str
    source_profile_id: UUID
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
    filters_applied_summary: dict
    unsupported_filters_ignored: list[str]
    fetch_mode: str
    used_existing_profile: bool
    douyin_account_connection_id: UUID
    selected_douyin_account_connection_id: UUID
    resolved_douyin_account_connection_id: UUID
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


class DouyinCurrentPageCaptureService:
    def __init__(self, db: Session):
        self.db = db

    def detect_current_page(self, account_connection_id: UUID) -> DouyinCurrentPageDetection:
        diagnostics_id = str(uuid4())
        snapshot = douyin_browser_context_registry.snapshot_current_page(account_connection_id)
        if not snapshot.available:
            return DouyinCurrentPageDetection(
                diagnostics_id=diagnostics_id,
                account_connection_id=account_connection_id,
                detected_page_type="unknown_page",
                supported_capture=False,
                recommended_action="open_managed_browser_profile",
                recommended_action_label="Open managed browser profile",
                operator_message="No live managed browser page is attached. Open or reopen this account profile, then navigate manually to a Douyin profile page.",
                page_url=snapshot.page_url,
                normalized_profile_url=None,
                title=snapshot.title,
                video_link_count=snapshot.video_link_count,
                runtime_context_id=snapshot.runtime_context_id,
                runtime_attach_status=snapshot.runtime_attach_status,
                page_recovery_status=snapshot.page_recovery_status,
                managed_runtime_status=snapshot.managed_runtime_status,
                detected_at=datetime.now(UTC),
                reason=snapshot.reason,
            )

        page_type = classify_current_page(
            page_url=snapshot.page_url,
            title=snapshot.title,
            body_text=snapshot.body_text,
            video_link_count=snapshot.video_link_count,
        )
        normalized_profile_url = profile_url_from_current_page(snapshot.page_url) if page_type in {"profile_page", "profile_feed_page"} else None
        supported_capture = page_type in {"profile_page", "profile_feed_page"} and normalized_profile_url is not None
        recommended_action, recommended_action_label, message = current_page_operator_guidance(page_type, supported_capture=supported_capture)
        logger.info(
            "douyin_current_page_detected",
            extra={
                "diagnostics_id": diagnostics_id,
                "account_connection_id": str(account_connection_id),
                "detected_page_type": page_type,
                "supported_capture": supported_capture,
                "video_link_count": snapshot.video_link_count,
                "runtime_context_id": snapshot.runtime_context_id,
            },
        )
        return DouyinCurrentPageDetection(
            diagnostics_id=diagnostics_id,
            account_connection_id=account_connection_id,
            detected_page_type=page_type,
            supported_capture=supported_capture,
            recommended_action=recommended_action,
            recommended_action_label=recommended_action_label,
            operator_message=message,
            page_url=snapshot.page_url,
            normalized_profile_url=normalized_profile_url,
            title=snapshot.title,
            video_link_count=snapshot.video_link_count,
            runtime_context_id=snapshot.runtime_context_id,
            runtime_attach_status=snapshot.runtime_attach_status,
            page_recovery_status=snapshot.page_recovery_status,
            managed_runtime_status=snapshot.managed_runtime_status,
            detected_at=datetime.now(UTC),
            reason=snapshot.reason,
        )

    def capture_current_page(
        self,
        *,
        account_connection_id: UUID,
        workspace_id: UUID | None,
        preset_name: str | None,
        filter_config: FilterConfig | None,
        persist: bool,
        max_videos: int = 50,
    ) -> DouyinCurrentPageCaptureSummary:
        diagnostics_id = str(uuid4())
        account_service = DouyinAccountService(self.db)
        account = account_service.get_account(account_connection_id)
        account_health = account_service.health_summary(account)
        warning_summary = account_health.warning_summary if isinstance(account_health.warning_summary, dict) else {}
        if warning_summary.get("profile_quarantine_state") in {"quarantined", "quarantined_recoverable", "quarantined_replaced"}:
            raise DouyinCurrentPageCaptureError(
                "profile_quarantined",
                "This Douyin browser profile is quarantined from normal current-page capture. Keep it open for reference only, then create and validate a fresh managed browser-backed profile for capture and Intake.",
                stage="profile_quarantine_gate",
                diagnostics_id=diagnostics_id,
            )
        snapshot = douyin_browser_context_registry.snapshot_current_page(account_connection_id)
        if not snapshot.available or snapshot.managed_runtime_status != "managed_runtime_active":
            raise DouyinCurrentPageCaptureError(
                "capture_not_ready_runtime_missing",
                "No active app-managed browser runtime is attached for this account. Open or reopen the saved browser profile first.",
                stage="snapshot_current_page",
                diagnostics_id=diagnostics_id,
            )
        page_type = classify_current_page(
            page_url=snapshot.page_url,
            title=snapshot.title,
            body_text=snapshot.body_text,
            video_link_count=snapshot.video_link_count,
        )
        profile_url = profile_url_from_current_page(snapshot.page_url) if page_type in {"profile_page", "profile_feed_page"} else None
        if profile_url is None:
            action, _, message = current_page_operator_guidance(page_type, supported_capture=False)
            raise DouyinCurrentPageCaptureError(
                "current_page_capture_not_supported",
                f"{message} Recommended action: {action}.",
                stage="classify_current_page",
                diagnostics_id=diagnostics_id,
            )

        payload = extract_profile_payload_from_browser_artifacts(
            html=snapshot.html,
            profile_url=profile_url,
            video_links=snapshot.video_links,
            page_title=snapshot.title,
            page_url=snapshot.page_url,
            max_videos=max_videos,
        )
        metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        metadata.update(
            {
                "source": "douyin_current_page_capture",
                "capture_model": "operator_assisted_current_page",
                "detected_page_type": page_type,
                "fetch_execution_path": "managed_browser_current_page",
                "final_execution_path_used": "managed_browser_current_page",
                "primary_execution_path": "managed_browser_current_page",
                "strategy_policy": "operator_current_page_only",
                "http_fallback_attempted": False,
                "browser_profile_available": True,
                "current_page_url": snapshot.page_url,
                "current_page_title": snapshot.title,
                "current_page_video_link_count": snapshot.video_link_count,
            }
        )
        payload["metadata"] = metadata
        try:
            ingest_summary = SourceIngestService(self.db).ingest_profile(
                workspace_id=workspace_id,
                profile_url=profile_url,
                source_platform=SourcePlatformEnum.DOUYIN,
                crawl_mode="operator_current_page_capture",
                adapter_payload_json=payload,
            )
        except SourceIngestError as exc:
            raise DouyinCurrentPageCaptureError(
                str(exc.code),
                exc.message,
                stage="canonical_ingest",
                diagnostics_id=diagnostics_id,
            ) from exc
        except SourceAdapterError as exc:
            raise DouyinCurrentPageCaptureError(
                str(exc.code),
                exc.message,
                stage="normalize_current_page_payload",
                diagnostics_id=diagnostics_id,
            ) from exc

        if ingest_summary.status != CrawlSessionStatus.COMPLETED or ingest_summary.source_profile_id is None:
            raise DouyinCurrentPageCaptureError(
                ingest_summary.error_code or "ingest_incomplete",
                ingest_summary.error_message or "Current page capture ingest did not complete.",
                stage="canonical_ingest",
                diagnostics_id=diagnostics_id,
            )
        source_profile = self.db.get(SourceProfile, UUID(str(ingest_summary.source_profile_id)))
        if source_profile is None:
            raise DouyinCurrentPageCaptureError(
                "source_profile_missing",
                "Current page capture completed but the source profile was not found.",
                stage="canonical_ingest",
                diagnostics_id=diagnostics_id,
            )

        result = CandidateEvaluationService(self.db).apply(
            preset_name=preset_name,
            filter_config=filter_config,
            source_profile_id=source_profile.id,
            persist=persist,
        )
        crawl_session_id = UUID(str(ingest_summary.crawl_session_id)) if ingest_summary.crawl_session_id else None
        fetch_stage_code = "success" if ingest_summary.videos_discovered_count > 0 else "true_zero_videos"
        fetch_stage_message = (
            "Current page capture imported visible profile videos."
            if ingest_summary.videos_discovered_count > 0
            else "Current page capture completed, but no visible videos were found. Scroll/load more manually and capture again."
        )
        warning = None
        if ingest_summary.videos_discovered_count == 0:
            warning = "No visible videos were imported from the current page. Scroll/load more manually and capture again."
        elif result.matched_count == 0:
            warning = "Videos were imported, but no candidates matched the current filters."

        if crawl_session_id is not None:
            crawl_session = self.db.get(CrawlSession, crawl_session_id)
            if crawl_session is not None:
                crawl_metadata = dict(crawl_session.metadata_json) if isinstance(crawl_session.metadata_json, dict) else {}
                crawl_metadata.update(
                    {
                        "diagnostics_id": diagnostics_id,
                        "fetch_mode": "operator_current_page_capture",
                        "detected_page_type": page_type,
                        "douyin_account_connection_id": str(account_connection_id),
                        "candidates_total_count": result.total_count,
                        "candidates_matched_count": result.matched_count,
                        "candidates_rejected_count": result.rejected_count,
                        "candidate_results_count": len(result.evaluations),
                    }
                )
                crawl_session.metadata_json = crawl_metadata
                self.db.commit()

        return DouyinCurrentPageCaptureSummary(
            success=True,
            diagnostics_id=diagnostics_id,
            account_connection_id=account_connection_id,
            detected_page_type=page_type,
            source_profile_id=source_profile.id,
            crawl_session_id=crawl_session_id,
            submitted_profile_url=profile_url,
            normalized_profile_identifier=source_profile.source_profile_external_id,
            videos_discovered_count=ingest_summary.videos_discovered_count,
            videos_created_count=ingest_summary.videos_created_count,
            videos_updated_count=ingest_summary.videos_updated_count,
            candidates_total_count=result.total_count,
            candidates_matched_count=result.matched_count,
            candidates_rejected_count=result.rejected_count,
            candidate_results_count=len(result.evaluations),
            filters_applied_summary=filter_config.to_dict() if filter_config is not None else {},
            unsupported_filters_ignored=[],
            fetch_mode="operator_current_page_capture",
            used_existing_profile=False,
            douyin_account_connection_id=account_connection_id,
            selected_douyin_account_connection_id=account_connection_id,
            resolved_douyin_account_connection_id=account_connection_id,
            fetch_stage="current_page_capture",
            fetch_stage_code=fetch_stage_code,
            fetch_stage_message=fetch_stage_message,
            parser_strategy=metadata.get("parse_strategy") if isinstance(metadata.get("parse_strategy"), str) else None,
            fetch_execution_path="managed_browser_current_page",
            fallback_from_execution_path=None,
            strategy_policy="operator_current_page_only",
            primary_execution_path="managed_browser_current_page",
            http_fallback_attempted=False,
            http_fallback_reason=None,
            preflight_ran=False,
            videos_normalized_count=ingest_summary.videos_discovered_count,
            videos_persisted_count=ingest_summary.videos_created_count + ingest_summary.videos_updated_count,
            next_suggested_route="/review-board?fresh=1",
            warning=warning,
            discovered_at=datetime.now(UTC),
            current_page_url=snapshot.page_url,
            current_page_title=snapshot.title,
            current_page_video_link_count=snapshot.video_link_count,
        )


def classify_current_page(*, page_url: str | None, title: str | None, body_text: str | None, video_link_count: int = 0) -> str:
    url = (page_url or "").strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = parsed.path.strip("/")
    lowered_title = (title or "").lower()
    lowered_body = (body_text or "").lower()
    lowered_url = url.lower()

    if "douyin.com" not in host and "iesdouyin.com" not in host:
        return "unsupported_page" if url else "unknown_page"
    if _looks_like_challenge_surface(lowered_title, lowered_body, lowered_url):
        return "challenge_page"
    if _looks_like_login_surface(lowered_title, lowered_body, lowered_url):
        return "login_page"
    if re.search(r"(^|/)video/[^/?#]+", path):
        return "video_detail_page"
    if re.search(r"(^|/)user/[^/?#]+", path) or path.startswith("@"):
        return "profile_feed_page" if video_link_count > 0 else "profile_page"
    if path in {"", "discover", "follow", "recommend"}:
        return "home_feed_page"
    return "unknown_page"


def profile_url_from_current_page(page_url: str | None) -> str | None:
    if not page_url:
        return None
    parsed = urlparse(page_url)
    if "douyin.com" not in parsed.netloc.lower() and "iesdouyin.com" not in parsed.netloc.lower():
        return None
    path = parsed.path.strip("/")
    user_match = re.search(r"user/([^/?#]+)", path)
    if user_match:
        return f"https://www.douyin.com/user/{user_match.group(1)}"
    if path.startswith("@"):
        handle = path.split("/", 1)[0]
        return f"https://www.douyin.com/{handle}"
    return None


def current_page_operator_guidance(page_type: str, *, supported_capture: bool) -> tuple[str, str, str]:
    if supported_capture:
        return (
            "capture_current_page",
            "Capture current page",
            "This Douyin profile page can be imported from the current managed browser page.",
        )
    if page_type == "login_page":
        return ("complete_login", "Complete login", "Complete login in the managed browser profile, then navigate to a target profile page.")
    if page_type == "challenge_page":
        return ("solve_challenge", "Solve challenge", "Solve the visible Douyin challenge in the managed browser, then capture again from the target profile page.")
    if page_type == "home_feed_page":
        return ("navigate_to_profile", "Navigate to profile", "Navigate manually to the target creator profile page before capturing.")
    if page_type == "video_detail_page":
        return ("navigate_to_profile", "Navigate to creator profile", "Video detail pages are detected, but profile import requires the creator profile page.")
    if page_type == "unsupported_page":
        return ("open_douyin_profile", "Open Douyin profile", "The current page is outside Douyin. Navigate to a Douyin profile page in the managed browser.")
    return ("inspect_current_page", "Inspect current page", "The current Douyin page is not recognized as a capturable profile page.")


def _looks_like_challenge_surface(title: str, body_text: str, page_url: str) -> bool:
    markers = (
        "captcha",
        "security check",
        "verify that you",
        "verify you are human",
        "验证码",
        "安全验证",
    )
    return any(marker in title or marker in body_text or marker in page_url for marker in markers)


def _looks_like_login_surface(title: str, body_text: str, page_url: str) -> bool:
    markers = (
        "login",
        "passport",
        "登录",
        "请先登录",
    )
    return any(marker in title or marker in body_text or marker in page_url for marker in markers)
