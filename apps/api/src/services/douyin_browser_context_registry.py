from __future__ import annotations

import base64
import logging
import json
import os
import shutil
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse
from uuid import UUID, uuid4

from src.core.settings import get_settings
from src.downloaders.errors import DownloadError, DownloadErrorCode

if TYPE_CHECKING:
    from src.downloaders.playwright_douyin_video_resolver import RankedPlayUrl

logger = logging.getLogger(__name__)

DOUYIN_BROWSER_LOGIN_URL = "https://www.douyin.com/"


@dataclass(frozen=True)
class PlaywrightAwemeDownloadResult:
    content: bytes | None
    play_url: str
    format_id: str
    watermark_free: bool
    watermark_authority: str | None = None
    height: int | None = None
    width: int | None = None
    bitrate: int | None = None
    codec: str | None = None
    fps: float | None = None
    hdr: bool | None = None
    author_handle: str | None = None
    author_display_name: str | None = None
    local_path: str | None = None
    size_bytes: int | None = None


AUTHENTICATED_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "sid_ucp_v1",
    "uid_tt",
    "uid_tt_ss",
}
_REQUEST_HEADER_SECRET_MARKERS = ("cookie", "token", "authorization", "credential", "csrf", "mstoken")
_REQUEST_HEADER_BLOCKLIST = {
    "cookie",
    "authorization",
    "proxy-authorization",
    "user-agent",
    "origin",
    "host",
    "referer",
    "sec-fetch-site",
    "sec-fetch-mode",
    "sec-fetch-dest",
    "sec-fetch-user",
    "sec-ch-ua",
    "sec-ch-ua-mobile",
    "sec-ch-ua-platform",
    "content-length",
}


class DouyinBrowserContextError(ValueError):
    pass


@dataclass(frozen=True)
class DouyinPersistentContextCapture:
    runtime_context_id: str
    browser_profile_id: str | None
    browser_profile_path: str | None
    cookie_header: str
    user_agent: str
    douyin_user_id: str | None
    metadata: dict | None
    browser_prevalidation_status: str | None
    browser_prevalidation_reason: str | None


@dataclass(frozen=True)
class DouyinBrowserContextSummary:
    runtime_context_id: str | None
    status: str
    account_connection_id: UUID | None
    connect_session_id: UUID | None
    started_at: datetime | None
    last_used_at: datetime | None
    last_validated_at: datetime | None
    reason: str | None = None
    browser_profile_id: str | None = None
    browser_profile_path: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None


@dataclass(frozen=True)
class DouyinBrowserWatchdogResult:
    checked_at: datetime
    result: str
    status: str
    runtime_context_id: str | None
    account_connection_id: UUID | None
    browser_profile_id: str | None
    browser_profile_path: str | None
    last_used_at: datetime | None
    last_validated_at: datetime | None
    runtime_reconciled: bool
    reason: str | None = None
    reconciled_reason: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None


@dataclass(frozen=True)
class DouyinBrowserContextValidationResult:
    available: bool
    status: str
    reason: str
    cookie_header: str | None = None
    user_agent: str | None = None
    runtime_context_id: str | None = None
    runtime_attach_status: str | None = None
    page_recovery_status: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None


@dataclass(frozen=True)
class DouyinBrowserProfileFetchResult:
    available: bool
    status: str
    reason: str
    runtime_context_id: str | None = None
    user_agent: str | None = None
    page_url: str | None = None
    title: str | None = None
    html: str | None = None
    video_link_count: int = 0
    video_links: list[str] = field(default_factory=list)
    response_documents: list[dict | list] = field(default_factory=list)
    response_records: list[dict] = field(default_factory=list)
    response_document_count: int = 0
    runtime_attach_status: str | None = None
    page_recovery_status: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None


@dataclass(frozen=True)
class DouyinBrowserReplayResult:
    available: bool
    status: str
    reason: str
    runtime_context_id: str | None = None
    response_url: str | None = None
    http_status: int | None = None
    content_type: str | None = None
    response_document: dict | list | None = None
    response_text: str | None = None
    runtime_attach_status: str | None = None
    page_recovery_status: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None


@dataclass(frozen=True)
class DouyinCurrentPageSnapshot:
    available: bool
    status: str
    reason: str
    runtime_context_id: str | None = None
    user_agent: str | None = None
    page_url: str | None = None
    title: str | None = None
    body_text: str | None = None
    html: str | None = None
    video_link_count: int = 0
    video_links: list[str] = field(default_factory=list)
    runtime_attach_status: str | None = None
    page_recovery_status: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None


@dataclass
class _ContextRecord:
    runtime_context_id: str
    browser_profile_id: str | None
    browser_profile_path: str | None
    persistent_profile: bool
    workspace_id: UUID
    connect_session_id: UUID
    account_connection_id: UUID | None
    playwright: object
    browser: object
    context: object
    page: object
    user_agent: str
    proxy_url: str | None
    status: str
    started_at: datetime
    last_used_at: datetime
    last_validated_at: datetime | None = None
    reason: str | None = None


class DouyinBrowserContextRegistry:
    """Runtime-only Playwright context registry for local development reuse."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        # Serialize Playwright sync-API usage across concurrent download jobs (thread-unsafe otherwise).
        self._playwright_op_lock = threading.RLock()
        self._records: dict[str, _ContextRecord] = {}

    def open_login_context_and_capture(
        self,
        *,
        workspace_id: UUID,
        connect_session_id: UUID,
        timeout_seconds: int,
        user_agent: str | None,
        proxy_url: str | None,
        cancelled: Callable[[], bool],
        account_connection_id: UUID | None = None,
        browser_profile_id: str | None = None,
        browser_profile_path: str | None = None,
        progress: Callable[[str, dict | None], None] | None = None,
    ) -> DouyinPersistentContextCapture:
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DouyinBrowserContextError("dependency_missing: install Playwright for API local browser connect") from exc

        settings = get_settings()
        resolved_user_agent = user_agent or settings.douyin_user_agent
        runtime_context_id = str(uuid4())
        existing = self._record_for_account(account_connection_id) if account_connection_id else None
        reused_existing_record: _ContextRecord | None = None
        if existing is not None:
            state = self._ensure_usable(existing)
            if state.status == "active":
                cookies = existing.context.cookies()
                if has_authenticated_douyin_cookies(cookies) and cookie_header_from_playwright_cookies(cookies):
                    return self._capture_from_record(existing)
                reused_existing_record = existing
                runtime_context_id = existing.runtime_context_id
        if account_connection_id:
            resolved_profile_id, resolved_profile_path_string = self.profile_identity_for_account(
                account_connection_id,
                browser_profile_id=(
                    browser_profile_id
                    or (reused_existing_record.browser_profile_id if reused_existing_record else None)
                ),
                browser_profile_path=(
                    browser_profile_path
                    or (reused_existing_record.browser_profile_path if reused_existing_record else None)
                ),
            )
        else:
            resolved_profile_id = browser_profile_id or self._profile_id_for_connect(workspace_id=workspace_id, connect_session_id=connect_session_id)
            resolved_profile_path_string = browser_profile_path or str(self._profile_path(resolved_profile_id))
        resolved_profile_path = (
            Path(reused_existing_record.browser_profile_path)
            if reused_existing_record and reused_existing_record.browser_profile_path
            else Path(resolved_profile_path_string)
        )
        playwright = reused_existing_record.playwright if reused_existing_record else None
        browser = reused_existing_record.browser if reused_existing_record else None
        context = reused_existing_record.context if reused_existing_record else None
        page = reused_existing_record.page if reused_existing_record else None
        deadline = time.monotonic() + timeout_seconds
        try:
            if reused_existing_record is None:
                ensure_windows_playwright_event_loop_policy()
                playwright = sync_playwright().start()
                launch_options: dict = {"headless": False}
                if proxy_url:
                    launch_options["proxy"] = {"server": proxy_url}
                if settings.douyin_persistent_browser_profile_enabled and resolved_profile_path:
                    context = self._launch_persistent_context(
                        playwright=playwright,
                        profile_path=resolved_profile_path,
                        user_agent=resolved_user_agent,
                        launch_options=launch_options,
                    )
                else:
                    try:
                        browser = playwright.chromium.launch(channel="chrome", **launch_options)
                    except Exception:
                        browser = playwright.chromium.launch(**launch_options)
                    context = browser.new_context(user_agent=resolved_user_agent)
                page, _ = self.get_or_create_live_page(context=context, preferred_page=None)
            else:
                page, _ = self.get_or_create_live_page(context=context, preferred_page=page)
            try:
                page.goto(DOUYIN_BROWSER_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
            except PlaywrightTimeoutError:
                logger.warning("Douyin persistent login page load timed out; continuing login wait")

            while time.monotonic() < deadline:
                if cancelled():
                    raise DouyinBrowserContextError("cancelled")
                try:
                    cookies = context.cookies()
                except PlaywrightError as exc:
                    raise DouyinBrowserContextError("browser_closed") from exc
                if has_authenticated_douyin_cookies(cookies):
                    if progress:
                        progress("login_detected", {"login_detected_at": datetime.now(UTC).isoformat(), "cookie_count": len(cookies)})
                    self._stabilize_authenticated_context(context=context, page=page, deadline=deadline, cancelled=cancelled, progress=progress)
                    if progress:
                        progress("validating_session", {"browser_prevalidation_started_at": datetime.now(UTC).isoformat()})
                    prevalidation_status, prevalidation_reason = self._prevalidate_record_context(context=context, page=page)
                    if progress:
                        progress(
                            "validating_session",
                            {
                                "browser_prevalidation_completed_at": datetime.now(UTC).isoformat(),
                                "browser_prevalidation_status": prevalidation_status,
                                "browser_prevalidation_reason": prevalidation_reason,
                            },
                        )
                    if prevalidation_status == "blocked" and progress:
                        progress(
                            "validation_retry_ready",
                            {
                                "post_login_blocked_retryable": True,
                                "browser_prevalidation_reason": prevalidation_reason,
                            },
                        )
                    if prevalidation_status == "login_required":
                        raise DouyinBrowserContextError(f"post_login_session_unstable:{prevalidation_reason}")
                    cookies = context.cookies()
                    cookie_header = cookie_header_from_playwright_cookies(cookies)
                    if not cookie_header:
                        raise DouyinBrowserContextError("authenticated_cookie_capture_empty")
                    try:
                        resolved_user_agent = page.evaluate("navigator.userAgent") or resolved_user_agent
                    except Exception:
                        pass
                    now = datetime.now(UTC)
                    if reused_existing_record is not None:
                        record = reused_existing_record
                        record.connect_session_id = connect_session_id
                        record.account_connection_id = account_connection_id
                        record.last_used_at = now
                        record.last_validated_at = now if prevalidation_status == "passed" else record.last_validated_at
                        record.reason = prevalidation_reason
                    else:
                        record = _ContextRecord(
                            runtime_context_id=runtime_context_id,
                            browser_profile_id=resolved_profile_id if settings.douyin_persistent_browser_profile_enabled else None,
                            browser_profile_path=str(resolved_profile_path) if resolved_profile_path else None,
                            persistent_profile=bool(settings.douyin_persistent_browser_profile_enabled and resolved_profile_path),
                            workspace_id=workspace_id,
                            connect_session_id=connect_session_id,
                            account_connection_id=account_connection_id,
                            playwright=playwright,
                            browser=browser,
                            context=context,
                            page=page,
                            user_agent=resolved_user_agent,
                            proxy_url=proxy_url,
                            status="active",
                            started_at=now,
                            last_used_at=now,
                            last_validated_at=now if prevalidation_status == "passed" else None,
                            reason=prevalidation_reason,
                        )
                        with self._lock:
                            self._records[runtime_context_id] = record
                    logger.info(
                        "Registered persistent Douyin browser context",
                        extra={"runtime_context_id": runtime_context_id, "connect_session_id": str(connect_session_id)},
                    )
                    return DouyinPersistentContextCapture(
                        runtime_context_id=runtime_context_id,
                        cookie_header=cookie_header,
                        user_agent=resolved_user_agent,
                        douyin_user_id=None,
                        metadata={
                            "cookie_count": len(cookies),
                            "login_url": DOUYIN_BROWSER_LOGIN_URL,
                            "runtime_context_id": runtime_context_id,
                            "browser_profile_id": resolved_profile_id if settings.douyin_persistent_browser_profile_enabled else None,
                            "browser_profile_path": str(resolved_profile_path) if resolved_profile_path else None,
                            "browser_profile_mode": "persistent_profile" if settings.douyin_persistent_browser_profile_enabled else "ephemeral_context",
                            "browser_prevalidation_status": prevalidation_status,
                            "browser_prevalidation_reason": prevalidation_reason,
                        },
                        browser_profile_id=resolved_profile_id if settings.douyin_persistent_browser_profile_enabled else None,
                        browser_profile_path=str(resolved_profile_path) if resolved_profile_path else None,
                        browser_prevalidation_status=prevalidation_status,
                        browser_prevalidation_reason=prevalidation_reason,
                    )
                time.sleep(2)
            raise DouyinBrowserContextError("login_timed_out")
        except Exception:
            if reused_existing_record is None:
                self._close_handles(playwright=playwright, browser=browser, context=context)
            raise

    def bind_context(self, runtime_context_id: str | None, account_connection_id: UUID) -> None:
        if not runtime_context_id:
            return
        with self._lock:
            record = self._records.get(runtime_context_id)
            if record is None:
                return
            record.account_connection_id = account_connection_id
            record.last_used_at = datetime.now(UTC)

    def _capture_from_record(self, record: _ContextRecord) -> DouyinPersistentContextCapture:
        cookies = record.context.cookies()
        cookie_header = cookie_header_from_playwright_cookies(cookies)
        try:
            user_agent = record.page.evaluate("navigator.userAgent") or record.user_agent
        except Exception:
            user_agent = record.user_agent
        now = datetime.now(UTC)
        record.last_used_at = now
        record.user_agent = user_agent
        if record.account_connection_id is not None:
            try:
                from src.downloaders.douyin_download_cookie_store import write_download_cookie_store_for_account

                write_download_cookie_store_for_account(
                    account_id=record.account_connection_id,
                    playwright_cookies=[
                        cookie
                        for cookie in cookies
                        if "douyin.com" in str(cookie.get("domain", "")).lower()
                    ],
                    user_agent=user_agent,
                )
            except Exception:
                logger.exception(
                    "download_cookie_store_flush_failed",
                    extra={"account_connection_id": str(record.account_connection_id)},
                )
        return DouyinPersistentContextCapture(
            runtime_context_id=record.runtime_context_id,
            browser_profile_id=record.browser_profile_id,
            browser_profile_path=record.browser_profile_path,
            cookie_header=cookie_header,
            user_agent=user_agent,
            douyin_user_id=None,
            metadata={
                "cookie_count": len(cookies),
                "login_url": DOUYIN_BROWSER_LOGIN_URL,
                "runtime_context_id": record.runtime_context_id,
                "browser_profile_id": record.browser_profile_id,
                "browser_profile_path": record.browser_profile_path,
                "browser_profile_mode": "persistent_profile" if record.persistent_profile else "ephemeral_context",
                "browser_profile_reused": True,
            },
            browser_prevalidation_status=None,
            browser_prevalidation_reason="live_profile_reused",
        )

    def export_playwright_cookies_for_download(
        self,
        *,
        workspace_id: UUID,
        account_connection_id: UUID,
        browser_profile_id: str | None,
        browser_profile_path: str | None,
        user_agent: str | None,
        proxy_url: str | None,
        allow_open_browser: bool = False,
    ) -> tuple[list[dict], str] | None:
        settings = get_settings()
        if not settings.douyin_persistent_browser_profile_enabled:
            return None
        if not browser_profile_id and not browser_profile_path:
            return None

        record = self._record_for_account(account_connection_id)
        if record is not None:
            state = self._ensure_usable(record)
            if state.status != "active":
                record = None

        if record is None:
            if not allow_open_browser:
                return None
            summary = self.open_profile_for_account(
                workspace_id=workspace_id,
                account_connection_id=account_connection_id,
                browser_profile_id=browser_profile_id,
                browser_profile_path=browser_profile_path,
                user_agent=user_agent,
                proxy_url=proxy_url,
            )
            if summary.status != "active":
                logger.warning(
                    "browser_download_cookies_unavailable",
                    extra={
                        "account_connection_id": str(account_connection_id),
                        "reason": summary.reason,
                        "status": summary.status,
                    },
                )
                return None
            record = self._record_for_account(account_connection_id)
            if record is None:
                return None

        cookies = record.context.cookies()
        if not has_authenticated_douyin_cookies(cookies):
            logger.warning(
                "browser_download_cookies_not_authenticated",
                extra={"account_connection_id": str(account_connection_id)},
            )
            return None

        douyin_cookies = [
            cookie
            for cookie in cookies
            if "douyin.com" in str(cookie.get("domain", "")).lower()
        ]
        if not douyin_cookies:
            return None

        try:
            resolved_user_agent = record.page.evaluate("navigator.userAgent") or record.user_agent
        except Exception:
            resolved_user_agent = user_agent or record.user_agent or settings.douyin_user_agent

        record.last_used_at = datetime.now(UTC)
        try:
            from src.downloaders.douyin_download_cookie_store import write_download_cookie_store_for_account

            write_download_cookie_store_for_account(
                account_id=account_connection_id,
                playwright_cookies=douyin_cookies,
                user_agent=resolved_user_agent,
            )
        except Exception:
            logger.exception(
                "download_cookie_store_flush_failed",
                extra={"account_connection_id": str(account_connection_id)},
            )
        return douyin_cookies, resolved_user_agent

    def has_any_active_context(self) -> bool:
        with self._lock:
            candidates = [record for record in self._records.values() if record.status == "active"]
        for record in candidates:
            state = self._ensure_usable(record)
            if state.status == "active":
                return True
        return False

    def has_active_context_for_account(self, account_connection_id: UUID) -> bool:
        record = self._record_for_account(account_connection_id)
        if record is None or record.status != "active":
            return False
        return self._ensure_usable(record).status == "active"

    @staticmethod
    def _is_recoverable_download_context_loss(reason: str | None, exc: BaseException | None = None) -> bool:
        if reason and (
            reason.startswith("browser_context_lost")
            or "TargetClosedError" in reason
            or "Target page, context or browser has been closed" in reason
        ):
            return True
        if exc is None:
            return False
        name = exc.__class__.__name__
        message = str(exc)
        return name == "TargetClosedError" or "TargetClosedError" in message or "has been closed" in message

    def _reopen_context_after_download_loss(self, record: _ContextRecord) -> _ContextRecord | None:
        account_connection_id = record.account_connection_id
        workspace_id = record.workspace_id
        profile_path = record.browser_profile_path
        if account_connection_id is None or workspace_id is None:
            logger.warning(
                "download_context_recovery_missing_identity",
                extra={
                    "runtime_context_id": record.runtime_context_id,
                    "has_account": account_connection_id is not None,
                    "has_workspace": workspace_id is not None,
                },
            )
            return None

        # Sticky recovery: reopen/attach first. open_profile_for_account kills orphans only on lock-style failures.
        # Download recovery stays headless so batch processing does not flash a window.
        settings = get_settings()
        headless = bool(getattr(settings, "douyin_playwright_download_headless", True))
        logger.warning(
            "download_context_recovery_reopen_without_preemptive_kill",
            extra={
                "account_connection_id": str(account_connection_id),
                "profile_path": profile_path,
                "reason": record.reason,
                "headless": headless,
            },
        )
        summary = self.open_profile_for_account(
            workspace_id=workspace_id,
            account_connection_id=account_connection_id,
            browser_profile_id=record.browser_profile_id,
            browser_profile_path=profile_path,
            user_agent=record.user_agent,
            proxy_url=record.proxy_url,
            allow_orphan_release=True,
            headless=headless,
        )
        if summary.status != "active":
            logger.warning(
                "download_context_recovery_open_failed",
                extra={
                    "account_connection_id": str(account_connection_id),
                    "reason": summary.reason,
                    "managed_runtime_status": summary.managed_runtime_status,
                },
            )
            return None
        recovered = self._record_for_account(account_connection_id)
        if recovered is None:
            return None
        logger.info(
            "download_context_recovery_succeeded",
            extra={
                "account_connection_id": str(account_connection_id),
                "runtime_context_id": recovered.runtime_context_id,
            },
        )
        return recovered

    def download_aweme_video(
        self,
        *,
        aweme_id: str,
        page_url: str | None = None,
        account_connection_id: UUID | None = None,
        timeout_ms: int = 90_000,
        allow_context_recovery: bool = True,
        destination_path: str | Path | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
        quality_profile: str = "balanced_processing",
        target_long_edge: int = 1920,
        preferred_candidate_url: str | None = None,
        preferred_format_id: str | None = None,
    ) -> "PlaywrightAwemeDownloadResult":
        with self._playwright_op_lock:
            return self._download_aweme_video_locked(
                aweme_id=aweme_id,
                page_url=page_url,
                account_connection_id=account_connection_id,
                timeout_ms=timeout_ms,
                allow_context_recovery=allow_context_recovery,
                destination_path=destination_path,
                on_progress=on_progress,
                quality_profile=quality_profile,
                target_long_edge=target_long_edge,
                preferred_candidate_url=preferred_candidate_url,
                preferred_format_id=preferred_format_id,
            )

    def discover_aweme_video(
        self,
        *,
        aweme_id: str,
        page_url: str | None = None,
        account_connection_id: UUID | None = None,
        timeout_ms: int = 30_000,
        quality_profile: str = "balanced_processing",
        target_long_edge: int = 1920,
    ) -> list["RankedPlayUrl"]:
        """Return playback candidates from the detail payload without transfer."""
        from src.downloaders.playwright_douyin_video_resolver import (
            _candidate_sort_key,
            extract_play_urls_from_aweme_payload,
        )

        with self._playwright_op_lock:
            record = self._record_for_account(account_connection_id) if account_connection_id else None
            if record is None:
                with self._lock:
                    active = [item for item in self._records.values() if item.status == "active"]
                record = active[0] if active else None
            if record is None:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    "No active Douyin Playwright browser context for metadata discovery",
                )
            state = self._ensure_usable(record)
            if state.status != "active":
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    f"Douyin Playwright context is not usable: {state.reason or state.status}",
                )
            page = record.page
            self._ensure_page_on_douyin_home(page=page, timeout_ms=timeout_ms)
            payload = self._fetch_aweme_detail_via_page(page=page, aweme_id=aweme_id)
            payloads = [payload] if isinstance(payload, dict) else []
            candidates: list["RankedPlayUrl"] = []
            seen: set[str] = set()
            for node in payloads:
                for item in extract_play_urls_from_aweme_payload(node):
                    if item.url not in seen:
                        seen.add(item.url)
                        candidates.append(item)
            candidates.sort(
                key=lambda item: _candidate_sort_key(
                    item,
                    quality_profile=quality_profile,
                    target_long_edge=target_long_edge,
                ),
                reverse=True,
            )
            return candidates

    def _download_aweme_video_locked(
        self,
        *,
        aweme_id: str,
        page_url: str | None = None,
        account_connection_id: UUID | None = None,
        timeout_ms: int = 90_000,
        allow_context_recovery: bool = True,
        destination_path: str | Path | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
        quality_profile: str = "balanced_processing",
        target_long_edge: int = 1920,
        preferred_candidate_url: str | None = None,
        preferred_format_id: str | None = None,
    ) -> "PlaywrightAwemeDownloadResult":
        from src.downloaders.playwright_douyin_video_resolver import (
            _candidate_sort_key,
            collect_aweme_payloads_from_render_data,
            extract_author_identity_from_aweme_payloads,
            extract_play_urls_from_aweme_payload,
            parse_render_data_aweme,
        )
        from src.downloaders.source_video_filename import parse_height_from_format_label

        record = self._record_for_account(account_connection_id) if account_connection_id else None
        if record is None and account_connection_id is not None:
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                "No active Douyin Playwright context for the selected account",
            )
        if record is None:
            with self._lock:
                active = [item for item in self._records.values() if item.status == "active"]
            record = active[0] if active else None
        if record is None:
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                "No active Douyin Playwright browser context. Keep the logged-in Chromium window open.",
            )

        state = self._ensure_usable(record)
        if state.status != "active":
            if allow_context_recovery and self._is_recoverable_download_context_loss(state.reason):
                recovered = self._reopen_context_after_download_loss(record)
                if recovered is not None:
                    return self._download_aweme_video_locked(
                        aweme_id=aweme_id,
                        page_url=page_url,
                        account_connection_id=recovered.account_connection_id or account_connection_id,
                        timeout_ms=timeout_ms,
                        allow_context_recovery=False,
                        destination_path=destination_path,
                        on_progress=on_progress,
                        quality_profile=quality_profile,
                        target_long_edge=target_long_edge,
                        preferred_candidate_url=preferred_candidate_url,
                        preferred_format_id=preferred_format_id,
                    )
            raise DownloadError(
                DownloadErrorCode.RESOLVE_FAILED,
                f"Douyin Playwright context is not usable: {state.reason or state.status}",
            )
        record = self._record_for_account(record.account_connection_id) if record.account_connection_id else record
        if record is None:
            raise DownloadError(DownloadErrorCode.RESOLVE_FAILED, "Douyin Playwright context disappeared")

        target_url = (page_url or "").strip() or f"https://www.douyin.com/video/{aweme_id}"
        page = record.page
        captured_payloads: list[dict] = []
        resolve_path = "detail_api"
        used_goto = False

        def _merge_candidates(payloads: list[dict]) -> list:
            ranked: list = []
            seen: set[str] = set()
            for payload in payloads:
                for item in extract_play_urls_from_aweme_payload(payload):
                    if item.url in seen:
                        continue
                    seen.add(item.url)
                    ranked.append(item)
            ranked.sort(
                key=lambda item: _candidate_sort_key(
                    item,
                    quality_profile=quality_profile,
                    target_long_edge=target_long_edge,
                ),
                reverse=True,
            )
            return ranked

        def _wait_for_clean_candidate_after_navigation() -> None:
            """Poll response captures and leave as soon as a clean URL exists.

            The previous unconditional 2.5 second sleep was paid on every page
            fallback even when the detail response arrived immediately. Keep the
            same upper budget for slow pages, but make the common path adaptive.
            """
            raw_budget = getattr(
                get_settings(),
                "douyin_playwright_media_settle_timeout_ms",
                2_500,
            )
            try:
                budget_ms = max(0, min(int(timeout_ms), int(raw_budget)))
            except (TypeError, ValueError):
                budget_ms = min(int(timeout_ms), 2_500)
            waited_ms = 0
            while waited_ms < budget_ms:
                if any(item.watermark_free for item in _merge_candidates(captured_payloads)):
                    return
                step_ms = min(200, budget_ms - waited_ms)
                page.wait_for_timeout(step_ms)
                waited_ms += step_ms

        def _on_response(response) -> None:
            try:
                url = response.url or ""
                if "aweme/detail" not in url and "aweme/v1/web/aweme/detail" not in url:
                    return
                if response.status != 200:
                    return
                data = response.json()
                if isinstance(data, dict):
                    captured_payloads.append(data)
            except Exception:
                return

        try:
            self._ensure_page_on_douyin_home(page=page, timeout_ms=timeout_ms)
            detail = self._fetch_aweme_detail_via_page(page=page, aweme_id=aweme_id)
            if isinstance(detail, dict):
                captured_payloads.append(detail)

            ranked_candidates = _merge_candidates(captured_payloads)
            if preferred_candidate_url or preferred_format_id:
                preferred = next(
                    (
                        item
                        for item in ranked_candidates
                        if item.url == preferred_candidate_url
                        or item.format_label == preferred_format_id
                    ),
                    None,
                )
                if preferred is not None:
                    ranked_candidates = [preferred] + [item for item in ranked_candidates if item.url != preferred.url]
            has_no_logo = any(item.watermark_free for item in ranked_candidates)

            # Escalate to full video navigation only when detail API lacks no-logo candidates.
            if not has_no_logo:
                resolve_path = "page_goto"
                used_goto = True
                page.on("response", _on_response)
                try:
                    try:
                        page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                        _wait_for_clean_candidate_after_navigation()
                        html = page.content()
                    except Exception as exc:
                        if allow_context_recovery and self._is_recoverable_download_context_loss(None, exc):
                            self._mark_invalid(record, f"browser_context_lost:{exc.__class__.__name__}")
                            recovered = self._reopen_context_after_download_loss(record)
                            if recovered is not None:
                                return self._download_aweme_video_locked(
                                    aweme_id=aweme_id,
                                    page_url=page_url,
                                    account_connection_id=recovered.account_connection_id or account_connection_id,
                                    timeout_ms=timeout_ms,
                                    allow_context_recovery=False,
                                    destination_path=destination_path,
                                    on_progress=on_progress,
                                    quality_profile=quality_profile,
                                    target_long_edge=target_long_edge,
                                    preferred_candidate_url=preferred_candidate_url,
                                    preferred_format_id=preferred_format_id,
                                )
                        raise
                    render_data = parse_render_data_aweme(html)
                    if render_data:
                        for node in collect_aweme_payloads_from_render_data(render_data):
                            if isinstance(node, dict):
                                captured_payloads.append(node)
                    ranked_candidates = _merge_candidates(captured_payloads)
                finally:
                    try:
                        page.remove_listener("response", _on_response)
                    except Exception:
                        pass

            if not ranked_candidates:
                raise DownloadError(
                    DownloadErrorCode.RESOLVE_FAILED,
                    "Playwright could not extract a Douyin media URL from the logged-in browser session",
                )

            def _transfer(candidates: list) -> tuple[bytes | None, str | None, int, str, str, bool]:
                if on_progress is not None:
                    on_progress(0, None)
                if destination_path is not None:
                    local_path, size_bytes, selected_url, selected_format, selected_clean = (
                        self._download_ranked_media_to_file(
                            page=page,
                            candidates=candidates,
                            user_agent=record.user_agent or "",
                            proxy_url=record.proxy_url,
                            timeout_ms=timeout_ms,
                            destination_path=destination_path,
                            on_progress=on_progress,
                            quality_profile=quality_profile,
                            target_long_edge=target_long_edge,
                            preferred_candidate_url=preferred_candidate_url,
                            preferred_format_id=preferred_format_id,
                        )
                    )
                    return None, local_path, size_bytes, selected_url, selected_format, selected_clean
                selected_content, selected_url, selected_format, selected_clean = self._download_ranked_media_bytes(
                    page=page,
                    candidates=candidates,
                    user_agent=record.user_agent or "",
                    timeout_ms=timeout_ms,
                    on_progress=on_progress,
                    quality_profile=quality_profile,
                )
                return selected_content, None, len(selected_content), selected_url, selected_format, selected_clean

            try:
                content, local_path, size_bytes, play_url, format_id, watermark_free = _transfer(ranked_candidates)
            except DownloadError as download_exc:
                if download_exc.code == DownloadErrorCode.CANCELLED:
                    raise
                if used_goto or download_exc.code != DownloadErrorCode.DOWNLOAD_FAILED:
                    raise
                # Detail-API URLs may be stale; one escalate to video page for fresher no-logo candidates.
                logger.warning(
                    "playwright_detail_api_download_failed_escalating_goto",
                    extra={"aweme_id": aweme_id, "error": download_exc.message},
                )
                resolve_path = "page_goto_after_detail_fail"
                used_goto = True
                page.on("response", _on_response)
                try:
                    page.goto(target_url, wait_until="domcontentloaded", timeout=timeout_ms)
                    _wait_for_clean_candidate_after_navigation()
                    html = page.content()
                    render_data = parse_render_data_aweme(html)
                    if render_data:
                        for node in collect_aweme_payloads_from_render_data(render_data):
                            if isinstance(node, dict):
                                captured_payloads.append(node)
                    ranked_candidates = _merge_candidates(captured_payloads)
                finally:
                    try:
                        page.remove_listener("response", _on_response)
                    except Exception:
                        pass
                if not ranked_candidates:
                    raise download_exc
                content, local_path, size_bytes, play_url, format_id, watermark_free = _transfer(ranked_candidates)

            record.last_used_at = datetime.now(UTC)
            author_handle, author_display_name = extract_author_identity_from_aweme_payloads(captured_payloads)
            selected_candidate = next(
                (
                    candidate
                    for candidate in ranked_candidates
                    if candidate.url == play_url or candidate.format_label == format_id
                ),
                None,
            )
            height = parse_height_from_format_label(format_id)
            if selected_candidate is not None:
                height = selected_candidate.height or height
            width = selected_candidate.width if selected_candidate is not None else None
            bitrate = selected_candidate.bitrate if selected_candidate is not None else None
            codec = selected_candidate.codec if selected_candidate is not None else None
            fps = selected_candidate.fps if selected_candidate is not None else None
            hdr = selected_candidate.hdr if selected_candidate is not None else None
            logger.info(
                "playwright_aweme_download_completed",
                extra={
                    "aweme_id": aweme_id,
                    "bytes": size_bytes,
                    "format_id": format_id,
                    "watermark_free": watermark_free,
                    "height": height,
                    "width": width,
                    "codec": codec,
                    "fps": fps,
                    "hdr": hdr,
                    "resolve_path": resolve_path,
                    "used_goto": used_goto,
                    "play_url_host": play_url.split("/")[2] if "://" in play_url else None,
                    "author_handle": author_handle,
                },
            )
            return PlaywrightAwemeDownloadResult(
                content=content,
                play_url=play_url,
                format_id=format_id,
                watermark_free=watermark_free,
                watermark_authority=(
                    "verified_playback_provenance" if watermark_free else "explicit_watermarked"
                ),
                height=height,
                width=width,
                bitrate=bitrate,
                codec=codec,
                fps=fps,
                hdr=hdr,
                author_handle=author_handle,
                author_display_name=author_display_name,
                local_path=local_path,
                size_bytes=size_bytes,
            )
        except Exception:
            if used_goto:
                try:
                    page.remove_listener("response", _on_response)
                except Exception:
                    pass
            raise

    def _ensure_page_on_douyin_home(self, *, page, timeout_ms: int) -> None:
        current = ""
        try:
            current = str(getattr(page, "url", "") or "")
        except Exception:
            current = ""
        if "douyin.com" in current.lower():
            return
        page.goto(DOUYIN_BROWSER_LOGIN_URL, wait_until="domcontentloaded", timeout=timeout_ms)

    def _fetch_aweme_detail_via_page(self, *, page, aweme_id: str):
        try:
            return page.evaluate(
                """async (awemeId) => {
                    const url = `https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=${awemeId}&device_platform=webapp&aid=6383`;
                    const res = await fetch(url, { credentials: 'include' });
                    if (!res.ok) return null;
                    return await res.json();
                }""",
                aweme_id,
            )
        except Exception as exc:
            logger.warning(
                "playwright_aweme_detail_api_failed",
                extra={"aweme_id": aweme_id, "error": exc.__class__.__name__},
            )
            return None

    def _download_ranked_media_to_file(
        self,
        *,
        page,
        candidates: list["RankedPlayUrl"],
        user_agent: str,
        proxy_url: str | None = None,
        timeout_ms: int,
        destination_path: str | Path,
        on_progress: Callable[[int, int | None], None] | None = None,
        quality_profile: str = "balanced_processing",
        target_long_edge: int = 1920,
    ) -> tuple[str, int, str, str, bool]:
        """Prefer a bounded-memory CDN transfer, retaining browser-body as fallback."""
        from src.downloaders.http import HttpAssetDownloader
        from src.downloaders.playwright_douyin_video_resolver import _candidate_sort_key

        settings = get_settings()
        allow_watermarked = bool(
            getattr(settings, "douyin_download_allow_watermarked_fallback", False)
        )
        ordered = sorted(
            candidates,
            key=lambda item: _candidate_sort_key(
                item,
                quality_profile=quality_profile,
                target_long_edge=target_long_edge,
            ),
            reverse=True,
        )
        allowed = [item for item in ordered if item.watermark_free]
        if allow_watermarked:
            allowed.extend(item for item in ordered if not item.watermark_free)
        if not allowed:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                "No no-logo candidates available for streamed Playwright transfer",
            )

        try:
            cookies = list(page.context.cookies() or [])
        except Exception:
            cookies = []
        destination = Path(destination_path).resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        downloader = HttpAssetDownloader(
            timeout_seconds=max(30, int(timeout_ms / 1000)),
            max_bytes=_configured_download_max_bytes(settings),
        )
        for attempt, candidate in enumerate(allowed, start=1):
            headers = {
                "Referer": "https://www.douyin.com/",
                "Origin": "https://www.douyin.com",
                "User-Agent": user_agent or "",
                "Accept": "*/*",
            }
            # Browser cookies are credentials.  Only forward cookies whose
            # domain/path actually match the selected CDN URL.
            cookie_header = cookie_header_for_url(cookies, candidate.url)
            if cookie_header:
                headers["Cookie"] = cookie_header
            candidate_path = destination.with_name(
                f".{destination.stem}.candidate-{attempt}{destination.suffix or '.mp4'}"
            )
            try:
                downloaded = downloader.fetch_to_file(
                    candidate.url,
                    candidate_path,
                    resume=True,
                    headers=headers,
                    proxy_url=proxy_url,
                    on_progress=on_progress,
                )
                if not downloaded.local_path or not Path(downloaded.local_path).is_file():
                    continue
                if not _file_has_video_stream(Path(downloaded.local_path)):
                    Path(downloaded.local_path).unlink(missing_ok=True)
                    logger.warning(
                        "playwright_media_stream_candidate_not_video",
                        extra={"attempt": attempt, "source": candidate.source},
                    )
                    continue
                os.replace(Path(downloaded.local_path), destination)
                size_bytes = destination.stat().st_size
                logger.info(
                    "playwright_media_stream_candidate_succeeded",
                    extra={
                        "attempt": attempt,
                        "source": candidate.source,
                        "watermark_free": candidate.watermark_free,
                        "height": candidate.height,
                        "bytes": size_bytes,
                    },
                )
                return (
                    str(destination),
                    size_bytes,
                    candidate.url,
                    candidate.format_label,
                    candidate.watermark_free,
                )
            except DownloadError as exc:
                if exc.code == DownloadErrorCode.CANCELLED:
                    raise
                logger.warning(
                    "playwright_media_stream_candidate_failed",
                    extra={
                        "attempt": attempt,
                        "source": candidate.source,
                        "error_code": str(exc.code),
                    },
                )

        # Some CDN URLs require Playwright's browser-owned request context. Keep
        # this compatibility path, but only after direct streaming candidates fail.
        content, play_url, format_id, watermark_free = self._download_ranked_media_bytes(
            page=page,
            candidates=ordered,
            user_agent=user_agent,
            timeout_ms=timeout_ms,
            allow_watermarked_fallback=allow_watermarked,
            on_progress=on_progress,
            quality_profile=quality_profile,
        )
        temp = destination.with_suffix(destination.suffix + ".part")
        temp.write_bytes(content)
        os.replace(temp, destination)
        return str(destination), destination.stat().st_size, play_url, format_id, watermark_free

    def _download_ranked_media_bytes(
        self,
        *,
        page,
        candidates: list[RankedPlayUrl],
        user_agent: str,
        timeout_ms: int,
        allow_watermarked_fallback: bool | None = None,
        on_progress: Callable[[int, int | None], None] | None = None,
        quality_profile: str = "balanced_processing",
        target_long_edge: int = 1920,
    ) -> tuple[bytes, str, str, bool]:
        """Download CDN bytes: prefer no-logo; watermarked only when explicitly allowed."""
        from src.core.settings import get_settings
        from src.downloaders.playwright_douyin_video_resolver import _candidate_sort_key

        if allow_watermarked_fallback is None:
            allow_watermarked_fallback = bool(
                getattr(get_settings(), "douyin_download_allow_watermarked_fallback", False)
            )

        ordered = sorted(
            candidates,
            key=lambda item: _candidate_sort_key(
                item,
                quality_profile=quality_profile,
                target_long_edge=target_long_edge,
            ),
            reverse=True,
        )
        no_logo = [item for item in ordered if item.watermark_free]
        watermarked = [item for item in ordered if not item.watermark_free]
        phases: list[tuple[str, list[RankedPlayUrl]]] = []
        if no_logo:
            phases.append(("no_logo", no_logo))
        if watermarked and allow_watermarked_fallback:
            phases.append(("watermarked_fallback", watermarked))
        if not phases:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                "No no-logo (bit_rate/play_addr) candidates available; watermarked fallback is disabled. "
                "Douyin download_addr streams usually include the platform logo. "
                "Refresh Douyin cookies or set DOUYIN_DOWNLOAD_ALLOW_WATERMARKED_FALLBACK=true.",
            )

        headers = {
            "Referer": "https://www.douyin.com/",
            "Origin": "https://www.douyin.com",
            "User-Agent": user_agent or "",
            "Accept": "*/*",
        }
        last_status: int | None = None
        attempted = 0
        max_bytes = _configured_download_max_bytes(get_settings())
        for phase_name, phase_candidates in phases:
            for candidate in phase_candidates:
                attempted += 1
                play_url = candidate.url
                if on_progress is not None:
                    on_progress(0, None)
                try:
                    response = page.context.request.get(play_url, headers=headers, timeout=timeout_ms)
                    status = int(getattr(response, "status", 0) or 0)
                    last_status = status
                    if status < 400:
                        content_length = _positive_header_int(
                            getattr(response, "headers", None),
                            "content-length",
                        )
                        if content_length is not None and content_length > max_bytes:
                            logger.warning(
                                "playwright_media_download_candidate_too_large",
                                extra={"attempt": attempted, "bytes": content_length},
                            )
                            continue
                        content = response.body()
                        if content and len(content) <= max_bytes:
                            logger.info(
                                "playwright_media_download_candidate_succeeded",
                                extra={
                                    "phase": phase_name,
                                    "attempt": attempted,
                                    "source": candidate.source,
                                    "watermark_free": candidate.watermark_free,
                                    "height": candidate.height,
                                    "bitrate": candidate.bitrate,
                                    "status": status,
                                    "bytes": len(content),
                                },
                            )
                            return content, play_url, candidate.format_label, candidate.watermark_free
                    logger.warning(
                        "playwright_media_download_candidate_rejected",
                        extra={
                            "phase": phase_name,
                            "attempt": attempted,
                            "source": candidate.source,
                            "watermark_free": candidate.watermark_free,
                            "status": status,
                        },
                    )
                except Exception as exc:
                    last_status = None
                    logger.warning(
                        "playwright_media_download_candidate_error",
                        extra={
                            "phase": phase_name,
                            "attempt": attempted,
                            "source": candidate.source,
                            "error": exc.__class__.__name__,
                        },
                    )

                in_page = self._fetch_cdn_bytes_in_page(
                    page=page,
                    play_url=play_url,
                    timeout_ms=timeout_ms,
                    max_bytes=max_bytes,
                )
                if in_page:
                    logger.info(
                        "playwright_media_download_in_page_succeeded",
                        extra={
                            "phase": phase_name,
                            "attempt": attempted,
                            "source": candidate.source,
                            "watermark_free": candidate.watermark_free,
                            "bytes": len(in_page),
                        },
                    )
                    return in_page, play_url, candidate.format_label, candidate.watermark_free

        if no_logo and not allow_watermarked_fallback and watermarked:
            raise DownloadError(
                DownloadErrorCode.DOWNLOAD_FAILED,
                f"No-logo download failed after {attempted} candidate(s) "
                f"(last HTTP {last_status or 'failed'}); watermarked fallback is disabled. "
                "Refresh Douyin cookies or set DOUYIN_DOWNLOAD_ALLOW_WATERMARKED_FALLBACK=true.",
            )
        raise DownloadError(
            DownloadErrorCode.DOWNLOAD_FAILED,
            f"Playwright media download HTTP {last_status or 'failed'} after {attempted} candidate(s)",
        )

    def _fetch_cdn_bytes_in_page(
        self,
        *,
        page,
        play_url: str,
        timeout_ms: int,
        max_bytes: int | None = None,
    ) -> bytes | None:
        bounded_max = max(1, int(max_bytes or 2_000_000_000))
        try:
            payload = page.evaluate(
                """
                async ({ url, timeoutMs, maxBytes }) => {
                  const controller = new AbortController();
                  const timeoutId = setTimeout(() => controller.abort("timeout"), timeoutMs);
                  try {
                    const response = await fetch(url, {
                      method: "GET",
                      credentials: "include",
                      headers: {
                        Referer: "https://www.douyin.com/",
                        Origin: "https://www.douyin.com",
                        Accept: "*/*",
                      },
                      signal: controller.signal,
                    });
                    if (!response.ok) {
                      return { ok: false, status: response.status };
                    }
                    const declared = Number(response.headers.get("content-length") || 0);
                    if (declared > maxBytes) {
                      return { ok: false, status: response.status, tooLarge: true };
                    }
                    const buffer = await response.arrayBuffer();
                    if (buffer.byteLength > maxBytes) {
                      return { ok: false, status: response.status, tooLarge: true };
                    }
                    const bytes = new Uint8Array(buffer);
                    let binary = "";
                    const chunk = 0x8000;
                    for (let i = 0; i < bytes.length; i += chunk) {
                      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
                    }
                    return { ok: true, status: response.status, base64: btoa(binary) };
                  } catch (error) {
                    return {
                      ok: false,
                      error: `${error && error.name ? error.name : "Error"}:${error && error.message ? error.message : String(error)}`,
                    };
                  } finally {
                    clearTimeout(timeoutId);
                  }
                }
                """,
                {
                    "url": play_url,
                    "timeoutMs": max(1_000, int(timeout_ms)),
                    "maxBytes": bounded_max,
                },
            )
        except Exception as exc:
            logger.warning(
                "playwright_media_in_page_fetch_exception",
                extra={"error": exc.__class__.__name__},
            )
            return None

        if not isinstance(payload, dict) or not payload.get("ok"):
            return None
        encoded = payload.get("base64")
        if not isinstance(encoded, str) or not encoded:
            return None
        try:
            content = base64.b64decode(encoded)
        except Exception:
            return None
        if len(content) > bounded_max:
            return None
        return content or None

    def open_profile_for_account(
        self,
        *,
        workspace_id: UUID,
        account_connection_id: UUID,
        browser_profile_id: str | None,
        browser_profile_path: str | None,
        user_agent: str | None,
        proxy_url: str | None,
        allow_orphan_release: bool = True,
        headless: bool = False,
    ) -> DouyinBrowserContextSummary:
        settings = get_settings()
        if not settings.douyin_persistent_browser_profile_enabled:
            return DouyinBrowserContextSummary(None, "none", account_connection_id, None, None, None, None, "persistent_profile_disabled")
        if not browser_profile_id and not browser_profile_path:
            return DouyinBrowserContextSummary(None, "none", account_connection_id, None, None, None, None, "no_persistent_profile")
        resolved_profile_id, resolved_profile_path_string = self.profile_identity_for_account(
            account_connection_id,
            browser_profile_id=browser_profile_id,
            browser_profile_path=browser_profile_path,
        )
        resolved_profile_path = Path(resolved_profile_path_string)
        existing = self._record_for_account(account_connection_id)
        if existing is not None:
            if self.profile_identity_matches(
                expected_profile_id=resolved_profile_id,
                expected_profile_path=str(resolved_profile_path),
                actual_profile_id=existing.browser_profile_id,
                actual_profile_path=existing.browser_profile_path,
            ):
                summary = self.summary_for_account(account_connection_id)
                if summary.managed_runtime_status == "managed_runtime_active":
                    return summary
            self.close_context(existing.runtime_context_id, reason="managed_runtime_stale_reconciled")
        self._close_other_managed_records_for_profile(
            account_connection_id=account_connection_id,
            profile_id=resolved_profile_id,
            profile_path=str(resolved_profile_path),
        )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return DouyinBrowserContextSummary(None, "invalid", account_connection_id, None, None, None, None, "dependency_missing", resolved_profile_id, str(resolved_profile_path))

        resolved_user_agent = user_agent or settings.douyin_user_agent
        playwright = None
        context = None
        try:
            ensure_windows_playwright_event_loop_policy()
            playwright = sync_playwright().start()
            launch_options: dict = {"headless": bool(headless)}
            if proxy_url:
                launch_options["proxy"] = {"server": proxy_url}
            context = self._launch_persistent_context(
                playwright=playwright,
                profile_path=resolved_profile_path,
                user_agent=resolved_user_agent,
                launch_options=launch_options,
            )
            try:
                # Persistent contexts often open with a blank page that settles briefly.
                time.sleep(0.4)
                pages = list(getattr(context, "pages", []) or [])
                preferred = pages[0] if pages else None
                page, page_recovery_status = self.get_or_create_live_page(context=context, preferred_page=preferred)
            except Exception as exc:
                raise DouyinBrowserContextError(f"managed_runtime_reopen_failed:{exc.__class__.__name__}") from exc
            now = datetime.now(UTC)
            runtime_context_id = str(uuid4())
            record = _ContextRecord(
                runtime_context_id=runtime_context_id,
                browser_profile_id=resolved_profile_id,
                browser_profile_path=str(resolved_profile_path),
                persistent_profile=True,
                workspace_id=workspace_id,
                connect_session_id=uuid4(),
                account_connection_id=account_connection_id,
                playwright=playwright,
                browser=None,
                context=context,
                page=page,
                user_agent=resolved_user_agent,
                proxy_url=proxy_url,
                status="active",
                started_at=now,
                last_used_at=now,
                reason=page_recovery_status if page_recovery_status != "live_runtime_attached" else "reopen_success",
            )
            with self._lock:
                self._records[runtime_context_id] = record
            summary = self.summary_for_account(account_connection_id)
            if summary.status != "active" or summary.runtime_context_id != runtime_context_id:
                self.close_context(runtime_context_id, reason="runtime_attach_failed_after_reopen")
                reason = summary.reason or "runtime_attach_failed"
                return DouyinBrowserContextSummary(
                    None,
                    "invalid",
                    account_connection_id,
                    None,
                    None,
                    None,
                    None,
                    reason,
                    resolved_profile_id,
                    str(resolved_profile_path),
                    managed_runtime_status="managed_runtime_stale",
                    profile_conflict_status=self._profile_conflict_status_for_reason(reason),
                )
            logger.info(
                "Reopened persistent Douyin browser profile",
                extra={"runtime_context_id": runtime_context_id, "account_connection_id": str(account_connection_id)},
            )
            return DouyinBrowserContextSummary(
                runtime_context_id,
                "active",
                account_connection_id,
                record.connect_session_id,
                record.started_at,
                record.last_used_at,
                record.last_validated_at,
                record.reason,
                resolved_profile_id,
                str(resolved_profile_path),
                managed_runtime_status="managed_runtime_active",
            )
        except Exception as exc:
            self._close_handles(playwright=playwright, browser=None, context=context)
            reason = self._classify_persistent_profile_open_error(exc)
            from src.services.douyin_playwright_orphan_release import (
                should_retry_playwright_open_after_orphan_release,
                terminate_orphaned_chromium_for_profile,
            )

            if should_retry_playwright_open_after_orphan_release(reason) and allow_orphan_release:
                killed = terminate_orphaned_chromium_for_profile(resolved_profile_path)
                logger.warning(
                    "retrying_open_after_orphan_playwright_release",
                    extra={
                        "account_connection_id": str(account_connection_id),
                        "killed": killed,
                        "reason": reason,
                        "profile_path": str(resolved_profile_path),
                    },
                )
                time.sleep(2.5)
                return self.open_profile_for_account(
                    workspace_id=workspace_id,
                    account_connection_id=account_connection_id,
                    browser_profile_id=browser_profile_id,
                    browser_profile_path=browser_profile_path,
                    user_agent=user_agent,
                    proxy_url=proxy_url,
                    allow_orphan_release=False,
                    headless=headless,
                )
            return DouyinBrowserContextSummary(
                None,
                "invalid",
                account_connection_id,
                None,
                None,
                None,
                None,
                reason,
                resolved_profile_id,
                str(resolved_profile_path),
                managed_runtime_status=self._managed_runtime_status_for_open_failure(reason),
                profile_conflict_status=self._profile_conflict_status_for_reason(reason),
            )

    def summary_for_account(self, account_connection_id: UUID) -> DouyinBrowserContextSummary:
        record = self._record_for_account(account_connection_id)
        if record is None:
            return DouyinBrowserContextSummary(
                None,
                "none",
                account_connection_id,
                None,
                None,
                None,
                None,
                managed_runtime_status="managed_runtime_missing",
            )
        state = self._ensure_usable(record)
        managed_runtime_status = self._managed_runtime_status_for_state(state.status)
        return DouyinBrowserContextSummary(
            runtime_context_id=record.runtime_context_id,
            status=state.status,
            account_connection_id=record.account_connection_id,
            connect_session_id=record.connect_session_id,
            started_at=record.started_at,
            last_used_at=record.last_used_at,
            last_validated_at=record.last_validated_at,
            reason=state.reason,
            browser_profile_id=record.browser_profile_id,
            browser_profile_path=record.browser_profile_path,
            managed_runtime_status=managed_runtime_status,
        )

    def watchdog_for_account(self, account_connection_id: UUID) -> DouyinBrowserWatchdogResult:
        checked_at = datetime.now(UTC)
        record = self._record_for_account(account_connection_id)
        if record is None:
            return DouyinBrowserWatchdogResult(
                checked_at=checked_at,
                result="missing",
                status="none",
                runtime_context_id=None,
                account_connection_id=account_connection_id,
                browser_profile_id=None,
                browser_profile_path=None,
                last_used_at=None,
                last_validated_at=None,
                runtime_reconciled=False,
                reason="no_runtime_context",
                managed_runtime_status="managed_runtime_missing",
            )

        previous_status = record.status
        previous_reason = record.reason
        state = self._ensure_usable(record)
        reconciled = previous_status != state.status or (
            state.status in {"stale", "invalid", "closed"} and previous_status == "active"
        )
        if state.status == "active":
            result = "healthy"
        elif state.status == "stale":
            result = "stale"
        elif state.status == "invalid":
            result = "invalid"
        elif state.status == "closed":
            result = "closed"
        else:
            result = "unavailable"

        return DouyinBrowserWatchdogResult(
            checked_at=checked_at,
            result=result,
            status=state.status,
            runtime_context_id=record.runtime_context_id,
            account_connection_id=record.account_connection_id,
            browser_profile_id=record.browser_profile_id,
            browser_profile_path=record.browser_profile_path,
            last_used_at=record.last_used_at,
            last_validated_at=record.last_validated_at,
            runtime_reconciled=reconciled,
            reason=state.reason,
            reconciled_reason=state.reason if reconciled and state.reason != previous_reason else None,
            managed_runtime_status=self._managed_runtime_status_for_state(state.status),
        )

    def validate_account_context(self, account_connection_id: UUID, *, validation_url: str | None = None) -> DouyinBrowserContextValidationResult:
        record = self._record_for_account(account_connection_id)
        if record is None:
            return DouyinBrowserContextValidationResult(
                False,
                "none",
                "no_live_browser_context",
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status="managed_runtime_missing",
            )
        state = self._ensure_usable(record)
        managed_runtime_status = self._managed_runtime_status_for_state(state.status)
        if state.status != "active":
            return DouyinBrowserContextValidationResult(
                False,
                state.status,
                state.reason or "browser_context_unavailable",
                runtime_context_id=record.runtime_context_id,
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status=managed_runtime_status,
            )
        with self._lock:
            target_url = validation_url or DOUYIN_BROWSER_LOGIN_URL
            page_recovery_status = state.reason if state.reason in {"page_reacquired_same_context", "page_created_same_context"} else "live_runtime_attached"
            for attempt_index in range(2):
                try:
                    record.page, current_page_status = self._page_for_record(record)
                    if current_page_status != "live_runtime_attached":
                        page_recovery_status = current_page_status
                    record.page.goto(target_url, wait_until="domcontentloaded", timeout=20_000)
                    status, reason = self._prevalidate_record_context(context=record.context, page=record.page)
                    cookie_header = cookie_header_from_playwright_cookies(record.context.cookies())
                    try:
                        user_agent = record.page.evaluate("navigator.userAgent") or record.user_agent
                    except Exception:
                        user_agent = record.user_agent
                    now = datetime.now(UTC)
                    record.last_used_at = now
                    record.last_validated_at = now if status == "passed" else record.last_validated_at
                    record.reason = reason
                    record.user_agent = user_agent
                    if status in {"passed", "uncertain"} and cookie_header:
                        return DouyinBrowserContextValidationResult(True, status, reason, cookie_header, user_agent, record.runtime_context_id, "managed_runtime_active", page_recovery_status, "managed_runtime_active")
                    return DouyinBrowserContextValidationResult(False, status, reason, cookie_header or None, user_agent, record.runtime_context_id, "managed_runtime_active", page_recovery_status, "managed_runtime_active")
                except Exception as exc:
                    if self._is_target_closed_page_error(exc) and attempt_index == 0:
                        record.page = None
                        page_recovery_status = "page_recreated_after_target_closed"
                        continue
                    self._mark_invalid(record, f"browser_context_error:{exc.__class__.__name__}")
                    return DouyinBrowserContextValidationResult(
                        False,
                        "invalid",
                        record.reason or "browser_context_error",
                        runtime_context_id=record.runtime_context_id,
                        runtime_attach_status="runtime_attach_failed",
                        page_recovery_status=page_recovery_status,
                        managed_runtime_status="managed_runtime_stale",
                    )

    def refresh_session_artifacts(self, account_connection_id: UUID) -> DouyinBrowserContextValidationResult:
        return self.validate_account_context(account_connection_id)

    def snapshot_current_page(self, account_connection_id: UUID) -> DouyinCurrentPageSnapshot:
        record = self._record_for_account(account_connection_id)
        if record is None:
            return DouyinCurrentPageSnapshot(
                False,
                "none",
                "no_live_browser_context",
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status="managed_runtime_missing",
            )
        state = self._ensure_usable(record)
        managed_runtime_status = self._managed_runtime_status_for_state(state.status)
        if state.status != "active":
            return DouyinCurrentPageSnapshot(
                False,
                state.status,
                state.reason or "browser_context_unavailable",
                runtime_context_id=record.runtime_context_id,
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status=managed_runtime_status,
            )
        with self._lock:
            page_recovery_status = "live_runtime_attached"
            try:
                record.page, page_recovery_status = self._page_for_record(record)
                page_url = str(getattr(record.page, "url", "") or "")
                try:
                    title = record.page.title()
                except Exception:
                    title = None
                try:
                    body_text = record.page.locator("body").inner_text(timeout=2_000)
                except Exception:
                    body_text = None
                try:
                    html = record.page.content()
                except Exception:
                    html = None
                try:
                    video_links = record.page.eval_on_selector_all(
                        'a[href*="/video/"]',
                        "elements => elements.map(element => element.href).filter(Boolean)",
                    )
                except Exception:
                    video_links = []
                try:
                    user_agent = record.page.evaluate("navigator.userAgent") or record.user_agent
                except Exception:
                    user_agent = record.user_agent
                now = datetime.now(UTC)
                record.last_used_at = now
                record.user_agent = user_agent
                return DouyinCurrentPageSnapshot(
                    True,
                    "active",
                    "current_page_snapshot_captured",
                    runtime_context_id=record.runtime_context_id,
                    user_agent=user_agent,
                    page_url=page_url,
                    title=title,
                    body_text=body_text,
                    html=html,
                    video_link_count=len(video_links) if isinstance(video_links, list) else 0,
                    video_links=video_links if isinstance(video_links, list) else [],
                    runtime_attach_status="managed_runtime_active",
                    page_recovery_status=page_recovery_status,
                    managed_runtime_status="managed_runtime_active",
                )
            except Exception as exc:
                self._mark_invalid(record, f"browser_current_page_error:{exc.__class__.__name__}")
                return DouyinCurrentPageSnapshot(
                    False,
                    "invalid",
                    record.reason or "browser_current_page_error",
                    runtime_context_id=record.runtime_context_id,
                    runtime_attach_status="runtime_attach_failed",
                    page_recovery_status=page_recovery_status,
                    managed_runtime_status="managed_runtime_stale",
                )

    def fetch_profile_page(
        self,
        account_connection_id: UUID,
        *,
        profile_url: str,
        timeout_ms: int = 30_000,
        settle_seconds: int | None = None,
        scroll_passes: int | None = None,
    ) -> DouyinBrowserProfileFetchResult:
        return self._fetch_page(
            account_connection_id,
            target_url=profile_url,
            timeout_ms=timeout_ms,
            settle_seconds=settle_seconds,
            scroll_passes=scroll_passes,
        )

    def fetch_detail_page(
        self,
        account_connection_id: UUID,
        *,
        detail_url: str,
        timeout_ms: int = 30_000,
        settle_seconds: int | None = None,
        scroll_passes: int | None = None,
    ) -> DouyinBrowserProfileFetchResult:
        return self._fetch_page(
            account_connection_id,
            target_url=detail_url,
            timeout_ms=timeout_ms,
            settle_seconds=settle_seconds,
            scroll_passes=scroll_passes,
        )

    def replay_request(
        self,
        account_connection_id: UUID,
        *,
        request_url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: str | None = None,
        timeout_ms: int = 20_000,
    ) -> DouyinBrowserReplayResult:
        record = self._record_for_account(account_connection_id)
        if record is None:
            return DouyinBrowserReplayResult(
                False,
                "none",
                "no_live_browser_context",
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status="managed_runtime_missing",
            )
        state = self._ensure_usable(record)
        managed_runtime_status = self._managed_runtime_status_for_state(state.status)
        if state.status != "active":
            return DouyinBrowserReplayResult(
                False,
                state.status,
                state.reason or "browser_context_unavailable",
                runtime_context_id=record.runtime_context_id,
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status=managed_runtime_status,
            )
        with self._lock:
            page_recovery_status = "live_runtime_attached"
            try:
                record.page, page_recovery_status = self._page_for_record(record)
                replay_payload = record.page.evaluate(
                    """
                    async ({ url, method, headers, body, timeoutMs }) => {
                      const controller = new AbortController();
                      const timeoutId = setTimeout(() => controller.abort("timeout"), timeoutMs);
                      try {
                        const response = await fetch(url, {
                          method,
                          headers,
                          body: body ?? undefined,
                          credentials: "include",
                          signal: controller.signal,
                        });
                        const text = await response.text();
                        return {
                          ok: response.ok,
                          status: response.status,
                          url: response.url,
                          contentType: response.headers.get("content-type") || "",
                          text,
                        };
                      } catch (error) {
                        return {
                          error: `${error && error.name ? error.name : "Error"}:${error && error.message ? error.message : String(error)}`,
                        };
                      } finally {
                        clearTimeout(timeoutId);
                      }
                    }
                    """,
                    {
                        "url": request_url,
                        "method": (method or "GET").upper(),
                        "headers": _sanitize_replay_headers(headers or {}),
                        "body": body,
                        "timeoutMs": max(1_000, int(timeout_ms)),
                    },
                )
                if not isinstance(replay_payload, dict):
                    return DouyinBrowserReplayResult(
                        False,
                        "invalid",
                        "browser_request_replay_invalid_payload",
                        runtime_context_id=record.runtime_context_id,
                        runtime_attach_status="managed_runtime_active",
                        page_recovery_status=page_recovery_status,
                        managed_runtime_status="managed_runtime_active",
                    )
                if replay_payload.get("error"):
                    return DouyinBrowserReplayResult(
                        False,
                        "invalid",
                        str(replay_payload["error"]),
                        runtime_context_id=record.runtime_context_id,
                        runtime_attach_status="managed_runtime_active",
                        page_recovery_status=page_recovery_status,
                        managed_runtime_status="managed_runtime_active",
                    )
                response_text = str(replay_payload.get("text") or "")
                response_document = _parse_json_response_payload(
                    response_text=response_text,
                    content_type=str(replay_payload.get("contentType") or ""),
                )
                record.last_used_at = datetime.now(UTC)
                return DouyinBrowserReplayResult(
                    True,
                    "active",
                    "browser_request_replayed",
                    runtime_context_id=record.runtime_context_id,
                    response_url=str(replay_payload.get("url") or request_url),
                    http_status=int(replay_payload.get("status")) if replay_payload.get("status") is not None else None,
                    content_type=str(replay_payload.get("contentType") or "") or None,
                    response_document=response_document,
                    response_text=response_text[:20_000] if response_text else None,
                    runtime_attach_status="managed_runtime_active",
                    page_recovery_status=page_recovery_status,
                    managed_runtime_status="managed_runtime_active",
                )
            except Exception as exc:
                self._mark_invalid(record, f"browser_request_replay_error:{exc.__class__.__name__}")
                return DouyinBrowserReplayResult(
                    False,
                    "invalid",
                    record.reason or "browser_request_replay_error",
                    runtime_context_id=record.runtime_context_id,
                    runtime_attach_status="runtime_attach_failed",
                    page_recovery_status=page_recovery_status,
                    managed_runtime_status="managed_runtime_stale",
                )

    def _fetch_page(
        self,
        account_connection_id: UUID,
        *,
        target_url: str,
        timeout_ms: int,
        settle_seconds: int | None,
        scroll_passes: int | None,
    ) -> DouyinBrowserProfileFetchResult:
        record = self._record_for_account(account_connection_id)
        if record is None:
            return DouyinBrowserProfileFetchResult(
                False,
                "none",
                "no_live_browser_context",
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status="managed_runtime_missing",
            )
        state = self._ensure_usable(record)
        managed_runtime_status = self._managed_runtime_status_for_state(state.status)
        if state.status != "active":
            return DouyinBrowserProfileFetchResult(
                False,
                state.status,
                state.reason or "browser_context_unavailable",
                runtime_context_id=record.runtime_context_id,
                runtime_attach_status="runtime_missing_reopen_required",
                managed_runtime_status=managed_runtime_status,
            )
        with self._lock:
            try:
                response_documents: list[dict | list] = []
                response_records: list[dict] = []

                def collect_response_document(response) -> None:
                    if len(response_documents) >= 20:
                        return
                    if len(response_records) >= 20:
                        return
                    request = getattr(response, "request", None)
                    response_url = str(getattr(response, "url", "") or "").lower()
                    if not any(marker in response_url for marker in ("douyin", "aweme", "post", "video", "user")):
                        return
                    headers = getattr(response, "headers", {}) or {}
                    content_type = str(headers.get("content-type", "") or "").lower()
                    if "json" not in content_type and not any(marker in response_url for marker in ("aweme", "post/item", "web/api")):
                        return
                    try:
                        parsed = response.json()
                    except Exception:
                        return
                    if isinstance(parsed, (dict, list)):
                        response_documents.append(parsed)
                        request_headers = {}
                        request_method = "GET"
                        request_url = str(getattr(response, "url", "") or "")
                        request_post_data = None
                        if request is not None:
                            try:
                                request_method = str(request.method or "GET").upper()
                            except Exception:
                                request_method = "GET"
                            try:
                                request_url = str(request.url or request_url)
                            except Exception:
                                pass
                            try:
                                request_headers = _sanitize_request_headers(request.headers or {})
                            except Exception:
                                request_headers = {}
                            try:
                                request_post_data = request.post_data
                            except Exception:
                                request_post_data = None
                        response_records.append(
                            {
                                "request_url": request_url,
                                "request_method": request_method,
                                "request_headers": request_headers,
                                "request_post_data": request_post_data[:4000] if isinstance(request_post_data, str) else None,
                                "response_url": str(getattr(response, "url", "") or ""),
                                "response_status": getattr(response, "status", None),
                                "response_content_type": content_type,
                                "response_document": parsed,
                            }
                        )

                record.page, page_recovery_status = self._page_for_record(record)
                try:
                    record.page.on("response", collect_response_document)
                except Exception:
                    pass
                try:
                    record.page.goto(target_url, wait_until="domcontentloaded", timeout=max(1_000, int(timeout_ms)))
                    try:
                        record.page.wait_for_load_state("networkidle", timeout=min(max(1_000, int(timeout_ms)), 10_000))
                    except Exception:
                        pass
                    settings = get_settings()
                    resolved_settle_seconds = settle_seconds
                    if resolved_settle_seconds is None:
                        resolved_settle_seconds = int(getattr(settings, "douyin_browser_profile_fetch_settle_seconds", 2))
                    resolved_settle_seconds = max(0, min(10, int(resolved_settle_seconds)))
                    resolved_scroll_passes = scroll_passes
                    if resolved_scroll_passes is None:
                        resolved_scroll_passes = int(getattr(settings, "douyin_browser_profile_fetch_scroll_passes", 4))
                    resolved_scroll_passes = max(0, min(12, int(resolved_scroll_passes)))
                    if resolved_settle_seconds:
                        record.page.wait_for_timeout(resolved_settle_seconds * 1000)
                    for _ in range(resolved_scroll_passes):
                        try:
                            record.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                            record.page.wait_for_timeout(1200)
                        except Exception:
                            break
                    try:
                        record.page.wait_for_load_state("networkidle", timeout=5_000)
                    except Exception:
                        pass
                finally:
                    try:
                        record.page.remove_listener("response", collect_response_document)
                    except Exception:
                        pass
                try:
                    html = record.page.content()
                except Exception:
                    html = None
                try:
                    title = (record.page.title() or "").strip() or None
                except Exception:
                    title = None
                page_url = record.page.url
                try:
                    user_agent = record.page.evaluate("navigator.userAgent") or record.user_agent
                except Exception:
                    user_agent = record.user_agent
                try:
                    video_links = list(
                        record.page.eval_on_selector_all(
                            'a[href*="/video/"]',
                            "els => Array.from(new Set(els.map(el => el.href || el.getAttribute('href')).filter(Boolean))).slice(0, 100)",
                        )
                    )
                except Exception:
                    video_links = []
                video_link_count = len(video_links)
                now = datetime.now(UTC)
                record.last_used_at = now
                record.user_agent = user_agent
                record.reason = "browser_profile_page_fetched"
                return DouyinBrowserProfileFetchResult(
                    True,
                    "active",
                    "browser_profile_page_fetched",
                    runtime_context_id=record.runtime_context_id,
                    user_agent=user_agent,
                    page_url=page_url,
                    title=title,
                    html=html,
                    video_link_count=video_link_count,
                    video_links=video_links,
                    response_documents=response_documents,
                    response_records=response_records,
                    response_document_count=len(response_documents),
                    runtime_attach_status="managed_runtime_active",
                    page_recovery_status=page_recovery_status,
                    managed_runtime_status="managed_runtime_active",
                )
            except Exception as exc:
                self._mark_invalid(record, f"browser_context_error:{exc.__class__.__name__}")
                return DouyinBrowserProfileFetchResult(
                    False,
                    "invalid",
                    record.reason or "browser_context_error",
                    runtime_context_id=record.runtime_context_id,
                    runtime_attach_status="runtime_attach_failed",
                    page_recovery_status=locals().get("page_recovery_status"),
                    managed_runtime_status="managed_runtime_stale",
                )

    def close_for_account(self, account_connection_id: UUID, *, reason: str) -> None:
        record = self._record_for_account(account_connection_id)
        if record is not None:
            self.close_context(record.runtime_context_id, reason=reason)

    def active_profile_ids(self) -> set[str]:
        with self._lock:
            records = [
                record
                for record in self._records.values()
                if record.status not in {"closed", "invalid"} and (record.browser_profile_id or record.browser_profile_path)
            ]
        profile_ids: set[str] = set()
        for record in records:
            if record.browser_profile_id:
                profile_ids.add(self._safe_profile_id(record.browser_profile_id))
            elif record.browser_profile_path:
                profile_ids.add(self._profile_id_from_path(record.browser_profile_path))
        return profile_ids

    def close_for_connect_session(self, connect_session_id: UUID, *, reason: str) -> None:
        with self._lock:
            context_ids = [record.runtime_context_id for record in self._records.values() if record.connect_session_id == connect_session_id]
        for context_id in context_ids:
            self.close_context(context_id, reason=reason)

    def close_context(self, runtime_context_id: str, *, reason: str) -> None:
        with self._lock:
            record = self._records.pop(runtime_context_id, None)
        if record is None:
            return
        record.status = "closed"
        record.reason = reason
        self._close_handles(playwright=record.playwright, browser=record.browser, context=record.context)
        logger.info("Closed Douyin browser context", extra={"runtime_context_id": runtime_context_id, "reason": reason})

    def _launch_persistent_context(self, *, playwright, profile_path: Path, user_agent: str, launch_options: dict):
        profile_path.mkdir(parents=True, exist_ok=True)
        context_options = dict(launch_options)
        context_options["user_agent"] = user_agent
        profile_path_string = str(profile_path)
        last_exc: Exception | None = None
        launch_attempts = [
            ("bundled_chromium", {}),
            ("chrome_channel", {"channel": "chrome"}),
        ]
        for attempt_name, channel_options in launch_attempts:
            for retry_index in range(2):
                try:
                    return playwright.chromium.launch_persistent_context(
                        profile_path_string,
                        **channel_options,
                        **context_options,
                    )
                except Exception as exc:
                    last_exc = exc
                    logger.warning(
                        "Douyin persistent browser profile launch failed",
                        extra={
                            "profile_path": profile_path_string,
                            "attempt": attempt_name,
                            "retry_index": retry_index,
                            "error_class": exc.__class__.__name__,
                        },
                    )
                    if not self._is_retryable_persistent_launch_error(exc):
                        break
                    time.sleep(1)
        if last_exc is not None:
            raise last_exc
        raise DouyinBrowserContextError("persistent_profile_launch_failed")

    def _is_retryable_persistent_launch_error(self, exc: Exception) -> bool:
        text = f"{exc.__class__.__name__}:{exc}".lower()
        return any(
            token in text
            for token in (
                "targetclosederror",
                "target page, context or browser has been closed",
                "browser has been closed",
                "process singleton",
                "singletonlock",
                "user data directory is already in use",
            )
        )

    def _is_target_closed_page_error(self, exc: Exception) -> bool:
        text = f"{exc.__class__.__name__}:{exc}".lower()
        return any(
            token in text
            for token in (
                "targetclosederror",
                "target page, context or browser has been closed",
                "browser has been closed",
            )
        )

    def _classify_persistent_profile_open_error(self, exc: Exception) -> str:
        if isinstance(exc, DouyinBrowserContextError):
            message = str(exc).strip()
            return message or "persistent_profile_open_failed"
        text = f"{exc.__class__.__name__}:{exc}".lower()
        if isinstance(exc, NotImplementedError):
            return "reopen_not_supported_current_runtime:NotImplementedError"
        if any(token in text for token in ("process singleton", "singletonlock", "user data directory is already in use")):
            return f"profile_locked_by_existing_process:{exc.__class__.__name__}"
        if any(token in text for token in ("targetclosederror", "target page, context or browser has been closed", "browser has been closed")):
            return f"first_page_closed_early:{exc.__class__.__name__}"
        if any(token in text for token in ("executable doesn't exist", "playwright install", "browser binary")):
            return f"reopen_not_supported_current_runtime:{exc.__class__.__name__}"
        if any(token in text for token in ("launch", "executable", "chrome", "chromium")):
            return f"browser_launch_failed:{exc.__class__.__name__}"
        return f"persistent_profile_open_failed:{exc.__class__.__name__}"

    def _profile_id_for_connect(self, *, workspace_id: UUID, connect_session_id: UUID) -> str:
        return f"{str(workspace_id)[:8]}-{str(connect_session_id)}"

    def _profile_id_for_account(self, account_connection_id: UUID) -> str:
        return f"account-{account_connection_id}"

    def profile_identity_for_account(
        self,
        account_connection_id: UUID,
        *,
        browser_profile_id: str | None = None,
        browser_profile_path: str | None = None,
    ) -> tuple[str, str]:
        resolved_profile_id = browser_profile_id if isinstance(browser_profile_id, str) and browser_profile_id else None
        if resolved_profile_id is None and browser_profile_path:
            resolved_profile_id = self._profile_id_from_path(browser_profile_path)
        if resolved_profile_id is None:
            resolved_profile_id = self._profile_id_for_account(account_connection_id)
        resolved_profile_path = str(Path(browser_profile_path)) if browser_profile_path else str(self._profile_path(resolved_profile_id))
        return resolved_profile_id, resolved_profile_path

    def profile_identity_matches(
        self,
        *,
        expected_profile_id: str | None,
        expected_profile_path: str | None,
        actual_profile_id: str | None,
        actual_profile_path: str | None,
    ) -> bool:
        expected_id = expected_profile_id or (self._profile_id_from_path(expected_profile_path) if expected_profile_path else None)
        actual_id = actual_profile_id or (self._profile_id_from_path(actual_profile_path) if actual_profile_path else None)
        if expected_id and actual_id and expected_id != actual_id:
            return False
        if expected_profile_path and actual_profile_path:
            return self._normalize_profile_path(expected_profile_path) == self._normalize_profile_path(actual_profile_path)
        return True

    def _profile_path(self, profile_id: str) -> Path:
        settings = get_settings()
        root = Path(settings.douyin_persistent_browser_profiles_root_dir)
        return root / self._safe_profile_id(profile_id)

    def _safe_profile_id(self, value: str) -> str:
        safe = "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)
        return safe[:120] or str(uuid4())

    def _profile_id_from_path(self, browser_profile_path: str | None) -> str:
        if not browser_profile_path:
            return str(uuid4())
        return self._safe_profile_id(Path(browser_profile_path).name)

    def _normalize_profile_path(self, value: str) -> str:
        return os.path.normcase(os.path.normpath(str(Path(value))))

    def _record_for_account(self, account_connection_id: UUID) -> _ContextRecord | None:
        with self._lock:
            candidates = [record for record in self._records.values() if record.account_connection_id == account_connection_id]
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item.last_used_at, reverse=True)[0]

    def _page_for_record(self, record: _ContextRecord):
        page, status = self.get_or_create_live_page(context=record.context, preferred_page=record.page)
        record.page = page
        return page, status

    def get_or_create_live_page(self, *, context, preferred_page):
        if self._page_is_usable(preferred_page):
            return preferred_page, "live_runtime_attached"
        saw_closed_page = preferred_page is not None
        try:
            pages = list(context.pages or [])
        except Exception as exc:
            pages = []
            saw_closed_page = True
            last_pages_error = exc
        else:
            last_pages_error = None
        for page in pages:
            if page is preferred_page:
                continue
            if self._page_is_usable(page):
                return page, "page_reacquired_same_context" if saw_closed_page else "live_runtime_attached"
            saw_closed_page = True
        last_new_page_error: Exception | None = None
        for _ in range(3):
            try:
                page = context.new_page()
                if self._page_is_usable(page):
                    return page, "page_created_same_context"
            except Exception as exc:
                last_new_page_error = exc
                time.sleep(0.25)
                try:
                    pages = list(context.pages or [])
                except Exception:
                    pages = []
                for candidate in pages:
                    if self._page_is_usable(candidate):
                        return candidate, "page_reacquired_same_context"
        if last_new_page_error is not None:
            raise last_new_page_error
        if last_pages_error is not None:
            raise last_pages_error
        raise DouyinBrowserContextError("page_recovery_failed")

    def _page_for_context(self, *, context, preferred_page):
        return self.get_or_create_live_page(context=context, preferred_page=preferred_page)

    def _page_is_usable(self, page) -> bool:
        if page is None:
            return False
        try:
            is_closed = getattr(page, "is_closed", None)
            if callable(is_closed) and is_closed() is True:
                return False
            getattr(page, "url", None)
            return True
        except Exception:
            return False

    def _managed_runtime_status_for_state(self, status: str | None) -> str:
        if status == "active":
            return "managed_runtime_active"
        if status in {"stale", "invalid", "closed"}:
            return "managed_runtime_stale"
        return "managed_runtime_missing"

    def _managed_runtime_status_for_open_failure(self, reason: str | None) -> str:
        if self._profile_conflict_status_for_reason(reason):
            return "profile_opened_outside_managed_runtime"
        if reason and (reason.startswith("managed_runtime_reopen_failed") or reason.startswith("first_page_closed_early")):
            return "managed_runtime_reopen_failed"
        if reason and reason.startswith("managed_runtime_stale"):
            return "managed_runtime_stale"
        return "managed_runtime_missing"

    def _profile_conflict_status_for_reason(self, reason: str | None) -> str | None:
        if not reason:
            return None
        if reason.startswith("profile_locked_by_existing_process"):
            return "profile_opened_outside_managed_runtime"
        return None

    def _close_other_managed_records_for_profile(self, *, account_connection_id: UUID, profile_id: str | None, profile_path: str | None) -> None:
        with self._lock:
            records = list(self._records.values())
        for record in records:
            if record.account_connection_id == account_connection_id:
                continue
            if self.profile_identity_matches(
                expected_profile_id=profile_id,
                expected_profile_path=profile_path,
                actual_profile_id=record.browser_profile_id,
                actual_profile_path=record.browser_profile_path,
            ):
                self.close_context(record.runtime_context_id, reason="profile_runtime_single_owner_reconciled")

    def _ensure_usable(self, record: _ContextRecord) -> DouyinBrowserContextSummary:
        settings = get_settings()
        now = datetime.now(UTC)
        idle_seconds = max(60, int(settings.douyin_browser_context_idle_timeout_seconds))
        lifetime_seconds = max(idle_seconds, int(settings.douyin_browser_context_max_lifetime_seconds))
        if (now - record.last_used_at).total_seconds() > idle_seconds:
            self.close_context(record.runtime_context_id, reason="idle_timeout")
            return DouyinBrowserContextSummary(record.runtime_context_id, "stale", record.account_connection_id, record.connect_session_id, record.started_at, record.last_used_at, record.last_validated_at, "idle_timeout")
        if (now - record.started_at).total_seconds() > lifetime_seconds:
            self.close_context(record.runtime_context_id, reason="max_lifetime_exceeded")
            return DouyinBrowserContextSummary(record.runtime_context_id, "stale", record.account_connection_id, record.connect_session_id, record.started_at, record.last_used_at, record.last_validated_at, "max_lifetime_exceeded")
        try:
            record.context.cookies()
            _, page_recovery_status = self._page_for_record(record)
        except Exception as exc:
            self._mark_invalid(record, f"browser_context_lost:{exc.__class__.__name__}")
            return DouyinBrowserContextSummary(record.runtime_context_id, "invalid", record.account_connection_id, record.connect_session_id, record.started_at, record.last_used_at, record.last_validated_at, record.reason)
        record.status = "active"
        if page_recovery_status != "live_runtime_attached":
            record.reason = page_recovery_status
        return DouyinBrowserContextSummary(record.runtime_context_id, "active", record.account_connection_id, record.connect_session_id, record.started_at, record.last_used_at, record.last_validated_at, record.reason)

    def _mark_invalid(self, record: _ContextRecord, reason: str) -> None:
        record.status = "invalid"
        record.reason = reason
        with self._lock:
            self._records.pop(record.runtime_context_id, None)
        self._close_handles(playwright=record.playwright, browser=record.browser, context=record.context)

    def _stabilize_authenticated_context(self, *, context, page, deadline: float, cancelled: Callable[[], bool], progress: Callable[[str, dict | None], None] | None) -> None:
        settings = get_settings()
        stabilize_seconds = max(2, min(20, int(getattr(settings, "douyin_browser_connect_stabilization_seconds", 8))))
        if progress:
            progress("stabilizing_auth", {"auth_stabilization_started_at": datetime.now(UTC).isoformat(), "stabilization_seconds": stabilize_seconds})
        end_at = min(deadline, time.monotonic() + stabilize_seconds)
        last_cookie_count = 0
        while time.monotonic() < end_at:
            if cancelled():
                raise DouyinBrowserContextError("cancelled")
            try:
                page.wait_for_load_state("networkidle", timeout=1500)
            except Exception:
                pass
            cookies = context.cookies()
            last_cookie_count = len(cookies)
            if not has_authenticated_douyin_cookies(cookies):
                raise DouyinBrowserContextError("auth_unstable:Authenticated cookies disappeared during stabilization")
            time.sleep(1)
        if progress:
            progress("stabilizing_auth", {"auth_stabilized_at": datetime.now(UTC).isoformat(), "post_stabilization_cookie_count": last_cookie_count})

    def _prevalidate_record_context(self, *, context, page) -> tuple[str, str]:
        cookies = context.cookies()
        if not has_authenticated_douyin_cookies(cookies):
            return "login_required", "authenticated_cookies_missing"
        try:
            page.goto(DOUYIN_BROWSER_LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
        except Exception:
            return "uncertain", "browser_prevalidation_navigation_uncertain"
        try:
            text = (page.content() or "").lower()
        except Exception:
            return "uncertain", "browser_prevalidation_content_unavailable"
        try:
            title = (page.title() or "").lower()
        except Exception:
            title = ""
        current_url = str(getattr(page, "url", "") or "").lower()
        combined = f"{title}\n{current_url}\n{text}"
        blocked_markers = (
            "captcha",
            "security check",
            "verify you",
            "verify that you",
            "安全验证",
            "验证码",
            "请完成验证",
            "滑块验证",
            "拖动滑块",
        )
        if any(marker in combined for marker in blocked_markers):
            return "blocked", "browser_context_blocked_response"
        if any(marker in combined for marker in ("passport", "login", "扫码登录", "登录后", "未登录")):
            cookies_after_navigation = context.cookies()
            if not has_authenticated_douyin_cookies(cookies_after_navigation):
                return "login_required", "authenticated_cookies_missing_after_prevalidation"
        cookies = context.cookies()
        if not has_authenticated_douyin_cookies(cookies):
            return "login_required", "authenticated_cookies_missing_after_prevalidation"
        positive_markers = (
            "douyin",
            "__universal_data_for_rehydration__",
            "render_data",
            "sigi_state",
            "aweme",
            "creator",
            "video",
            "抖音",
        )
        if any(marker in combined for marker in positive_markers):
            return "passed", "authenticated_context_reachable"
        return "uncertain", "browser_prevalidation_no_positive_page_signal"

    def _close_handles(self, *, playwright, browser, context) -> None:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
        if playwright is not None:
            try:
                playwright.stop()
            except Exception:
                pass


def has_authenticated_douyin_cookies(cookies: list[dict]) -> bool:
    names = {str(cookie.get("name", "")).lower() for cookie in cookies}
    return bool(names.intersection(AUTHENTICATED_COOKIE_NAMES))


def _file_has_video_stream(path: Path) -> bool:
    binary = shutil.which("ffprobe")
    if binary is None:
        # DownloadService owns the fail-closed authority when ffprobe is absent;
        # do not convert a host configuration issue into candidate exhaustion here.
        return True
    try:
        completed = subprocess.run(
            [
                binary,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type,width,height",
                "-of",
                "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
            shell=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    if completed.returncode != 0:
        return False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False
    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list):
        return False
    for stream in streams:
        if not isinstance(stream, dict) or stream.get("codec_type") != "video":
            continue
        try:
            if int(stream.get("width") or 0) > 0 and int(stream.get("height") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def cookie_header_from_playwright_cookies(cookies: list[dict]) -> str:
    pairs: list[tuple[str, str]] = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).lower()
        name = str(cookie.get("name", ""))
        value = str(cookie.get("value", ""))
        if not name or not value:
            continue
        if "douyin.com" not in domain:
            continue
        pairs.append((name, value))
    return "; ".join(f"{name}={value}" for name, value in sorted(pairs))


def cookie_header_for_url(cookies: list[dict], url: str) -> str:
    """Build a cookie header using normal domain/path matching for one URL.

    The older helper intentionally returns all Douyin cookies for browser
    bootstrap.  Media CDN transfers need stricter matching so a session cookie
    is never sent to an unrelated host.
    """
    parsed = urlparse((url or "").strip())
    host = (parsed.hostname or "").lower().rstrip(".")
    path = parsed.path or "/"
    secure = parsed.scheme.lower() == "https"
    pairs: list[tuple[str, str]] = []
    for cookie in cookies:
        domain = str(cookie.get("domain", "")).strip().lower().lstrip(".").rstrip(".")
        name = str(cookie.get("name", "")).strip()
        value = str(cookie.get("value", ""))
        cookie_path = str(cookie.get("path", "/") or "/")
        if not host or not domain or not name or not value:
            continue
        if not (host == domain or host.endswith(f".{domain}")):
            continue
        normalized_cookie_path = cookie_path if cookie_path.startswith("/") else f"/{cookie_path}"
        if normalized_cookie_path != "/":
            if not path.startswith(normalized_cookie_path):
                continue
            if not (
                path == normalized_cookie_path
                or normalized_cookie_path.endswith("/")
                or path[len(normalized_cookie_path) :].startswith("/")
            ):
                continue
        if cookie.get("secure") and not secure:
            continue
        pairs.append((name, value))
    return "; ".join(f"{name}={value}" for name, value in sorted(pairs))


def _positive_header_int(headers: object, name: str) -> int | None:
    if headers is None:
        return None
    try:
        raw = headers.get(name)  # type: ignore[attr-defined]
    except Exception:
        return None
    try:
        value = int(str(raw or "").strip())
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _configured_download_max_bytes(settings: object) -> int:
    raw = getattr(settings, "douyin_download_max_bytes", 2_000_000_000)
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        return 2_000_000_000
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 2_000_000_000
    return value if value > 0 else 2_000_000_000


def ensure_windows_playwright_event_loop_policy() -> None:
    if os.name != "nt":
        return
    import asyncio

    policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_cls is None:
        return
    current_policy = asyncio.get_event_loop_policy()
    if isinstance(current_policy, policy_cls):
        return
    asyncio.set_event_loop_policy(policy_cls())


def _sanitize_request_headers(headers: dict) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key, value in headers.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        lowered = key_text.lower()
        if lowered in _REQUEST_HEADER_BLOCKLIST:
            continue
        if any(marker in lowered for marker in _REQUEST_HEADER_SECRET_MARKERS):
            continue
        value_text = str(value or "").strip()
        if not value_text:
            continue
        safe[key_text] = value_text[:500]
    return safe


def _sanitize_replay_headers(headers: dict[str, str]) -> dict[str, str]:
    allowed: dict[str, str] = {}
    for key, value in _sanitize_request_headers(headers).items():
        if key.lower().startswith("sec-"):
            continue
        allowed[key] = value
    return allowed


def _parse_json_response_payload(*, response_text: str, content_type: str) -> dict | list | None:
    if not response_text:
        return None
    lowered_content_type = str(content_type or "").lower()
    stripped = response_text.lstrip()
    if "json" not in lowered_content_type and not stripped.startswith(("{", "[")):
        return None
    try:
        parsed = json.loads(response_text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, (dict, list)):
        return parsed
    return None


douyin_browser_context_registry = DouyinBrowserContextRegistry()
