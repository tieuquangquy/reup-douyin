from __future__ import annotations

import importlib.util
import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from src.core.settings import get_settings
from src.db.bootstrap import ensure_default_workspace
from src.db.session import get_session_factory
from src.enums import (
    DouyinAccountConnectionStatus,
    DouyinAccountHealthStatus,
    DouyinAccountWarningLevel,
    DouyinBrowserConnectSessionStatus,
)
from src.models.source_accounts import DouyinBrowserConnectSession
from src.schemas.douyin_accounts import (
    DouyinAccountCreateRequest,
    DouyinAccountUpdateRequest,
    DouyinBrowserConnectActiveSessionResponse,
    DouyinBrowserConnectResetResponse,
    DouyinBrowserConnectSessionResponse,
    DouyinBrowserConnectStartRequest,
)
from src.services.douyin_browser_context_registry import (
    DouyinBrowserContextError,
    douyin_browser_context_registry,
)
from src.services.douyin_account_service import DouyinAccountError, DouyinAccountService

logger = logging.getLogger(__name__)

DOUYIN_BROWSER_LOGIN_URL = "https://www.douyin.com/"
AUTHENTICATED_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "sid_ucp_v1",
    "uid_tt",
    "uid_tt_ss",
}
RUNNING_CONNECT_STATUSES = {
    DouyinBrowserConnectSessionStatus.PENDING,
    DouyinBrowserConnectSessionStatus.LAUNCHING_BROWSER,
    DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN,
    DouyinBrowserConnectSessionStatus.CAPTURING_SESSION,
    DouyinBrowserConnectSessionStatus.VALIDATING,
}


class DouyinBrowserConnectError(ValueError):
    pass


@dataclass(frozen=True)
class DouyinBrowserSessionCaptureResult:
    cookie_header: str
    user_agent: str
    douyin_user_id: str | None = None
    metadata: dict | None = None
    browser_prevalidation_status: str | None = None
    browser_prevalidation_reason: str | None = None
    runtime_context_id: str | None = None
    browser_profile_id: str | None = None
    browser_profile_path: str | None = None


class PlaywrightDouyinBrowserSessionCapture:
    def capture(
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
    ) -> DouyinBrowserSessionCaptureResult:
        ensure_windows_playwright_event_loop_policy()
        settings = get_settings()
        if settings.douyin_persistent_browser_context_enabled:
            try:
                capture = douyin_browser_context_registry.open_login_context_and_capture(
                    workspace_id=workspace_id,
                    connect_session_id=connect_session_id,
                    account_connection_id=account_connection_id,
                    browser_profile_id=browser_profile_id,
                    browser_profile_path=browser_profile_path,
                    timeout_seconds=timeout_seconds,
                    user_agent=user_agent,
                    proxy_url=proxy_url,
                    cancelled=cancelled,
                    progress=progress,
                )
            except DouyinBrowserContextError as exc:
                raise DouyinBrowserConnectError(str(exc)) from exc
            return DouyinBrowserSessionCaptureResult(
                cookie_header=capture.cookie_header,
                user_agent=capture.user_agent,
                douyin_user_id=capture.douyin_user_id,
                metadata=capture.metadata,
                browser_prevalidation_status=capture.browser_prevalidation_status,
                browser_prevalidation_reason=capture.browser_prevalidation_reason,
                runtime_context_id=capture.runtime_context_id,
                browser_profile_id=capture.browser_profile_id,
                browser_profile_path=capture.browser_profile_path,
            )
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise DouyinBrowserConnectError(
                "dependency_missing: install Playwright for API local browser connect, then retry browser connect"
            ) from exc

        resolved_user_agent = user_agent or settings.douyin_user_agent
        deadline = time.monotonic() + timeout_seconds
        try:
            with sync_playwright() as playwright:
                launch_options: dict = {"headless": False}
                if proxy_url:
                    launch_options["proxy"] = {"server": proxy_url}
                browser = None
                context = None
                try:
                    try:
                        browser = playwright.chromium.launch(channel="chrome", **launch_options)
                    except Exception:
                        browser = playwright.chromium.launch(**launch_options)
                except Exception as exc:
                    raise DouyinBrowserConnectError(playwright_runtime_error("launch_failed", exc)) from exc

                try:
                    context = browser.new_context(user_agent=resolved_user_agent)
                    page = context.new_page()
                    try:
                        page.goto(DOUYIN_BROWSER_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                    except PlaywrightTimeoutError:
                        logger.warning("Douyin browser login page load timed out; continuing login wait")
                    while time.monotonic() < deadline:
                        if cancelled():
                            raise DouyinBrowserConnectError("cancelled")
                        try:
                            cookies = context.cookies()
                        except PlaywrightError as exc:
                            raise DouyinBrowserConnectError(playwright_runtime_error("browser_closed", exc)) from exc
                        if has_authenticated_douyin_cookies(cookies):
                            if progress:
                                progress("login_detected", {"login_detected_at": datetime.now(UTC).isoformat(), "cookie_count": len(cookies)})
                            self._stabilize_authenticated_context(
                                context=context,
                                page=page,
                                deadline=deadline,
                                cancelled=cancelled,
                                progress=progress,
                            )
                            if progress:
                                progress("validating_session", {"browser_prevalidation_started_at": datetime.now(UTC).isoformat()})
                            prevalidation_status, prevalidation_reason = self._prevalidate_in_browser_context(context=context, page=page)
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
                                raise DouyinBrowserConnectError(f"post_login_session_unstable:{prevalidation_reason}")
                            cookies = context.cookies()
                            cookie_header = cookie_header_from_playwright_cookies(cookies)
                            if not cookie_header:
                                raise DouyinBrowserConnectError("authenticated_cookie_capture_empty")
                            try:
                                resolved_user_agent = page.evaluate("navigator.userAgent") or resolved_user_agent
                            except Exception:
                                pass
                            return DouyinBrowserSessionCaptureResult(
                                cookie_header=cookie_header,
                                user_agent=resolved_user_agent,
                                metadata={
                                    "cookie_count": len(cookies),
                                    "login_url": DOUYIN_BROWSER_LOGIN_URL,
                                    "browser_profile_mode": "ephemeral_context",
                                    "browser_prevalidation_status": prevalidation_status,
                                    "browser_prevalidation_reason": prevalidation_reason,
                                },
                                browser_prevalidation_status=prevalidation_status,
                                browser_prevalidation_reason=prevalidation_reason,
                            )
                        time.sleep(2)
                    raise DouyinBrowserConnectError("login_timed_out")
                finally:
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
        except DouyinBrowserConnectError:
            raise
        except Exception as exc:
            raise DouyinBrowserConnectError(playwright_runtime_error("runtime_probe_failed", exc)) from exc

    def _stabilize_authenticated_context(
        self,
        *,
        context,
        page,
        deadline: float,
        cancelled: Callable[[], bool],
        progress: Callable[[str, dict | None], None] | None,
    ) -> None:
        settings = get_settings()
        stabilize_seconds = max(2, min(20, int(getattr(settings, "douyin_browser_connect_stabilization_seconds", 8))))
        if progress:
            progress(
                "stabilizing_auth",
                {"auth_stabilization_started_at": datetime.now(UTC).isoformat(), "stabilization_seconds": stabilize_seconds},
            )
        end_at = min(deadline, time.monotonic() + stabilize_seconds)
        last_cookie_count = 0
        while time.monotonic() < end_at:
            if cancelled():
                raise DouyinBrowserConnectError("cancelled")
            try:
                page.wait_for_load_state("networkidle", timeout=1500)
            except Exception:
                pass
            cookies = context.cookies()
            last_cookie_count = len(cookies)
            if not has_authenticated_douyin_cookies(cookies):
                raise DouyinBrowserConnectError("auth_unstable:Authenticated cookies disappeared during stabilization")
            time.sleep(1)
        if progress:
            progress(
                "stabilizing_auth",
                {"auth_stabilized_at": datetime.now(UTC).isoformat(), "post_stabilization_cookie_count": last_cookie_count},
            )

    def _prevalidate_in_browser_context(self, *, context, page) -> tuple[str, str]:
        cookies = context.cookies()
        if not has_authenticated_douyin_cookies(cookies):
            return "login_required", "authenticated_cookies_missing"
        try:
            page.goto(DOUYIN_BROWSER_LOGIN_URL, wait_until="domcontentloaded", timeout=20_000)
        except Exception:
            # If navigation is noisy but authenticated cookies remain, keep the result retryable instead of hard-blocking.
            return "uncertain", "browser_prevalidation_navigation_uncertain"
        try:
            text = (page.content() or "").lower()
        except Exception:
            return "uncertain", "browser_prevalidation_content_unavailable"
        if any(marker in text for marker in ("captcha", "security check", "verify you", "verify that you")):
            return "blocked", "browser_context_blocked_response"
        cookies = context.cookies()
        if not has_authenticated_douyin_cookies(cookies):
            return "login_required", "authenticated_cookies_missing_after_prevalidation"
        return "passed", "authenticated_context_reachable"


class DouyinBrowserConnectService:
    def __init__(
        self,
        db: Session,
        *,
        session_factory: sessionmaker[Session] | None = None,
        capture_runner: PlaywrightDouyinBrowserSessionCapture | None = None,
    ):
        self.db = db
        self._session_factory = session_factory or get_session_factory()
        self._capture_runner = capture_runner or PlaywrightDouyinBrowserSessionCapture()

    def start_connect(self, request: DouyinBrowserConnectStartRequest) -> DouyinBrowserConnectSession:
        workspace_id = request.workspace_id or ensure_default_workspace(self.db).id
        target_account = None
        target_metadata: dict = {}
        if request.account_connection_id is not None:
            try:
                target_account = DouyinAccountService(self.db).get_account(request.account_connection_id)
            except DouyinAccountError as exc:
                raise DouyinBrowserConnectError("account_connection_not_found: Cannot reopen browser profile for missing Douyin account.") from exc
            workspace_id = target_account.workspace_id
            target_metadata = dict(target_account.metadata_json or {})
            canonical_profile_id, canonical_profile_path = douyin_browser_context_registry.profile_identity_for_account(
                target_account.id,
                browser_profile_id=target_metadata.get("browser_profile_id") if isinstance(target_metadata.get("browser_profile_id"), str) else None,
                browser_profile_path=target_metadata.get("browser_profile_path") if isinstance(target_metadata.get("browser_profile_path"), str) else None,
            )
            target_metadata["browser_profile_id"] = canonical_profile_id
            target_metadata["browser_profile_path"] = canonical_profile_path
            target_metadata["browser_profile_mode"] = "persistent_profile"
        active_session = self._get_latest_active_looking_session(workspace_id)
        if active_session is not None:
            if self._finalize_if_stale(active_session):
                active_session = None
            elif self._active_session_matches_target(active_session, request.account_connection_id):
                logger.info(
                    "Reusing active Douyin browser connect session",
                    extra={"connect_session_id": str(active_session.id), "workspace_id": str(workspace_id)},
                )
                return active_session
            else:
                raise DouyinBrowserConnectError(
                    "active_session_exists: A different browser profile session is already running. Cancel or reset it before opening this account profile."
                )
        runtime_available, runtime_error_code, runtime_error_message = self._runtime_probe(require_launch=True)
        if not runtime_available:
            raise DouyinBrowserConnectError(
                f"{runtime_error_code}: {runtime_error_message}"
                if runtime_error_code
                else "browser_runtime_unavailable: Local browser runtime is not ready."
            )
        session = DouyinBrowserConnectSession(
            workspace_id=workspace_id,
            status=DouyinBrowserConnectSessionStatus.LAUNCHING_BROWSER,
            mode="browser_assisted",
            display_name=request.display_name or (target_account.display_name if target_account else None),
            is_default=request.is_default or bool(target_account.is_default if target_account else False),
            user_agent=request.user_agent or (target_account.user_agent if target_account else None),
            proxy_url=request.proxy_url or (target_account.proxy_url if target_account else None),
            started_at=datetime.now(UTC),
            derived_account_id=request.account_connection_id,
            metadata_json={
                "timeout_seconds": request.timeout_seconds,
                "login_url": DOUYIN_BROWSER_LOGIN_URL,
                "target_account_connection_id": str(request.account_connection_id) if request.account_connection_id else None,
                "browser_profile_id": target_metadata.get("browser_profile_id"),
                "browser_profile_path": target_metadata.get("browser_profile_path"),
                "browser_profile_mode": target_metadata.get("browser_profile_mode") or ("persistent_profile" if request.account_connection_id else None),
            },
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)

        thread = threading.Thread(target=self._run_background, args=(session.id,), daemon=True)
        thread.start()
        logger.info("Started Douyin browser connect session", extra={"connect_session_id": str(session.id)})
        return session

    def get_active_session(self, workspace_id: UUID | None = None) -> DouyinBrowserConnectSession | None:
        resolved_workspace_id = workspace_id or ensure_default_workspace(self.db).id
        session = self._get_latest_active_looking_session(resolved_workspace_id)
        if session is None:
            return None
        self._finalize_if_stale(session)
        return session

    def get_session(self, connect_session_id: UUID) -> DouyinBrowserConnectSession:
        session = self.db.get(DouyinBrowserConnectSession, connect_session_id)
        if session is None:
            raise DouyinBrowserConnectError("Douyin browser connect session not found")
        self._finalize_if_stale(session)
        return session

    def cancel_session(self, connect_session_id: UUID) -> DouyinBrowserConnectSession:
        session = self.get_session(connect_session_id)
        if session.status in {
            DouyinBrowserConnectSessionStatus.COMPLETED,
            DouyinBrowserConnectSessionStatus.FAILED,
            DouyinBrowserConnectSessionStatus.CANCELLED,
        }:
            return session
        session.status = DouyinBrowserConnectSessionStatus.CANCELLED
        session.finished_at = self._now()
        session.updated_at = session.finished_at
        session.last_error = "cancelled:Connect cancelled by operator"
        douyin_browser_context_registry.close_for_connect_session(session.id, reason="connect_cancelled")
        self.db.commit()
        self.db.refresh(session)
        return session

    def restart_session(
        self,
        connect_session_id: UUID,
        request: DouyinBrowserConnectStartRequest,
    ) -> DouyinBrowserConnectSession:
        session = self.get_session(connect_session_id)
        restart_request = request
        if session.derived_account_id is not None:
            if request.account_connection_id is not None and request.account_connection_id != session.derived_account_id:
                raise DouyinBrowserConnectError("restart_target_mismatch: Restart cannot switch to a different Douyin account profile.")
            if request.account_connection_id is None:
                restart_request = request.model_copy(update={"account_connection_id": session.derived_account_id})
        if session.status in RUNNING_CONNECT_STATUSES:
            session.status = DouyinBrowserConnectSessionStatus.CANCELLED
            session.finished_at = self._now()
            session.updated_at = session.finished_at
            session.last_error = "cancelled:Connect cancelled by force restart"
            douyin_browser_context_registry.close_for_connect_session(session.id, reason="connect_force_restart")
            self.db.commit()
        return self.start_connect(restart_request)

    def reset_connect_state(self, workspace_id: UUID | None = None) -> DouyinBrowserConnectResetResponse:
        resolved_workspace_id = workspace_id or ensure_default_workspace(self.db).id
        sessions = (
            self.db.query(DouyinBrowserConnectSession)
            .filter(
                DouyinBrowserConnectSession.workspace_id == resolved_workspace_id,
                DouyinBrowserConnectSession.status.in_(tuple(RUNNING_CONNECT_STATUSES)),
            )
            .order_by(DouyinBrowserConnectSession.created_at.desc())
            .all()
        )
        now = self._now()
        affected_session_ids: list[UUID] = []
        for session in sessions:
            session.status = DouyinBrowserConnectSessionStatus.CANCELLED
            session.finished_at = now
            session.updated_at = now
            session.last_error = "reset_by_operator:Browser connect state reset by operator recovery action"
            douyin_browser_context_registry.close_for_connect_session(session.id, reason="browser_connect_reset")
            metadata = dict(session.metadata_json or {})
            metadata["reset_by_operator_at"] = now.isoformat()
            metadata["reset_scope"] = "browser_connect_state_only"
            session.metadata_json = metadata
            affected_session_ids.append(session.id)
        if affected_session_ids:
            self.db.commit()
            logger.info(
                "Reset Douyin browser connect state",
                extra={"workspace_id": str(resolved_workspace_id), "reset_count": len(affected_session_ids)},
            )
        return DouyinBrowserConnectResetResponse(
            reset_count=len(affected_session_ids),
            affected_session_ids=affected_session_ids,
            resulting_state=DouyinBrowserConnectSessionStatus.CANCELLED,
            can_start_new=True,
            warning=None if affected_session_ids else "No active browser connect sessions needed reset.",
        )

    def retry_validation(self, connect_session_id: UUID) -> DouyinBrowserConnectSession:
        session = self.get_session(connect_session_id)
        if session.derived_account_id is None:
            raise DouyinBrowserConnectError("validation_retry_unavailable: No derived account exists for this connect session.")
        error_code, _ = self._parse_error(session.last_error)
        if session.status not in RUNNING_CONNECT_STATUSES and error_code != "validation_retry_ready":
            raise DouyinBrowserConnectError("validation_retry_unavailable: Connect session is not waiting for validation retry.")
        metadata = dict(session.metadata_json or {})
        metadata["browser_connect_phase"] = "validating_session"
        metadata["validation_attempt_count"] = int(metadata.get("validation_attempt_count", 0)) + 1
        metadata["validation_retry_started_at"] = self._now().isoformat()
        session.metadata_json = metadata
        session.status = DouyinBrowserConnectSessionStatus.VALIDATING
        session.updated_at = self._now()
        self.db.commit()

        account_service = DouyinAccountService(self.db)
        account, valid, reason = account_service.validate_account(session.derived_account_id, validation_source="connect_retry")
        self.db.refresh(session)
        session.finished_at = self._now()
        session.updated_at = session.finished_at
        if valid:
            session.status = DouyinBrowserConnectSessionStatus.COMPLETED
            session.last_error = None
        else:
            session.status = DouyinBrowserConnectSessionStatus.FAILED
            session.last_error = f"validation_failed:{reason}"
        metadata = dict(session.metadata_json or {})
        metadata["validation_retry_finished_at"] = session.finished_at.isoformat()
        metadata["validation_retry_result"] = reason
        session.metadata_json = metadata
        self.db.commit()
        self.db.refresh(session)
        return session

    def to_active_response(self, session: DouyinBrowserConnectSession | None) -> DouyinBrowserConnectActiveSessionResponse:
        return DouyinBrowserConnectActiveSessionResponse(session=self.to_response(session) if session is not None else None)

    def to_response(self, session: DouyinBrowserConnectSession) -> DouyinBrowserConnectSessionResponse:
        self._finalize_if_stale(session)
        account_response = None
        if session.derived_account_id is not None:
            try:
                account_service = DouyinAccountService(self.db)
                account_response = account_service.to_response(account_service.get_account(session.derived_account_id))
            except DouyinAccountError:
                account_response = None
        error_code, error_message = self._parse_error(session.last_error)
        runtime_available, _, _ = self._runtime_probe(require_launch=False)
        phase = self._phase_for_status(session.status)
        phase = self._phase_for_session(session=session, fallback_phase=phase, error_code=error_code)
        outcome = self._outcome_for(status=session.status, error_code=error_code)
        phase_deadline_at = self._phase_deadline_at(session=session, phase=phase)
        remaining_seconds = self._remaining_seconds(phase_deadline_at)
        timed_out_at = session.finished_at if outcome == "timed_out" else None
        is_stale, stale_reason = self._stale_state(session)
        age_seconds = self._age_seconds(session.started_at)
        can_cancel = session.status in RUNNING_CONNECT_STATUSES
        can_resume = can_cancel and not is_stale
        metadata = dict(session.metadata_json or {})
        validation_attempt_count = int(metadata.get("validation_attempt_count", 0))
        can_retry_validation = error_code == "validation_retry_ready" and session.derived_account_id is not None
        live_context_available = bool(account_response and account_response.browser_context_available)
        can_resume_browser_session = can_resume or (can_retry_validation and live_context_available)
        can_retry = session.status in {
            DouyinBrowserConnectSessionStatus.FAILED,
            DouyinBrowserConnectSessionStatus.CANCELLED,
            DouyinBrowserConnectSessionStatus.COMPLETED,
        }
        return DouyinBrowserConnectSessionResponse(
            id=session.id,
            workspace_id=session.workspace_id,
            status=session.status,
            mode=session.mode,
            display_name=session.display_name,
            started_at=session.started_at,
            finished_at=session.finished_at,
            last_error=session.last_error,
            error_code=error_code,
            error_message=error_message,
            outcome=outcome,
            phase=phase,
            phase_deadline_at=phase_deadline_at,
            remaining_seconds=remaining_seconds,
            timed_out_at=timed_out_at,
            age_seconds=age_seconds,
            is_stale=is_stale,
            stale_reason=stale_reason,
            can_retry=can_retry,
            can_cancel=can_cancel,
            can_resume=can_resume,
            can_force_restart=session.status != DouyinBrowserConnectSessionStatus.COMPLETED,
            can_resume_browser_session=can_resume_browser_session,
            can_retry_validation=can_retry_validation,
            should_keep_browser_open=session.status in RUNNING_CONNECT_STATUSES or can_resume_browser_session,
            validation_attempt_count=validation_attempt_count,
            next_action=self._next_action(session.status.value, error_code),
            runtime_available=runtime_available,
            manual_fallback_available=bool(getattr(get_settings(), "douyin_enable_legacy_manual_import", False)),
            derived_account_id=session.derived_account_id,
            account=account_response,
            instructions="A real Douyin browser window is opened locally. Complete login there; QR login is supported if Douyin shows QR on that page.",
            login_url=DOUYIN_BROWSER_LOGIN_URL,
        )

    def _run_background(self, connect_session_id: UUID) -> None:
        db = self._session_factory()
        try:
            session = db.get(DouyinBrowserConnectSession, connect_session_id)
            if session is None:
                return
            self._set_status(db, session, DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN)

            def cancelled() -> bool:
                db.expire_all()
                current = db.get(DouyinBrowserConnectSession, connect_session_id)
                return current is None or current.status not in RUNNING_CONNECT_STATUSES

            def progress(phase: str, metadata: dict | None = None) -> None:
                db.expire_all()
                current = db.get(DouyinBrowserConnectSession, connect_session_id)
                if current is None or current.status not in RUNNING_CONNECT_STATUSES:
                    return
                current_metadata = dict(current.metadata_json or {})
                current_metadata["browser_connect_phase"] = phase
                current_metadata.update(metadata or {})
                current.metadata_json = current_metadata
                if phase in {"login_detected", "stabilizing_auth"}:
                    current.status = DouyinBrowserConnectSessionStatus.CAPTURING_SESSION
                if phase == "validating_session":
                    current.status = DouyinBrowserConnectSessionStatus.VALIDATING
                current.updated_at = self._now()
                db.commit()

            session_metadata = dict(session.metadata_json or {})
            target_account_id = session.derived_account_id
            browser_profile_id = session_metadata.get("browser_profile_id") if isinstance(session_metadata.get("browser_profile_id"), str) else None
            browser_profile_path = session_metadata.get("browser_profile_path") if isinstance(session_metadata.get("browser_profile_path"), str) else None
            if target_account_id and (browser_profile_id or browser_profile_path):
                account_service = DouyinAccountService(db)
                existing = account_service.get_account(target_account_id)
                existing_metadata = dict(existing.metadata_json or {})
                canonical_profile_id, canonical_profile_path = douyin_browser_context_registry.profile_identity_for_account(
                    existing.id,
                    browser_profile_id=existing_metadata.get("browser_profile_id") if isinstance(existing_metadata.get("browser_profile_id"), str) else browser_profile_id,
                    browser_profile_path=existing_metadata.get("browser_profile_path") if isinstance(existing_metadata.get("browser_profile_path"), str) else browser_profile_path,
                )
                if not douyin_browser_context_registry.profile_identity_matches(
                    expected_profile_id=canonical_profile_id,
                    expected_profile_path=canonical_profile_path,
                    actual_profile_id=browser_profile_id,
                    actual_profile_path=browser_profile_path,
                ):
                    raise DouyinBrowserConnectError(
                        "profile_identity_mismatch: Refusing to reopen this Douyin account with a different browser profile."
                    )
                progress(
                    "opening_managed_runtime",
                    {
                        "browser_profile_id": canonical_profile_id,
                        "browser_profile_mode": "persistent_profile",
                        "managed_runtime_bootstrap_started_at": self._now().isoformat(),
                    },
                )
                summary = douyin_browser_context_registry.open_profile_for_account(
                    workspace_id=session.workspace_id,
                    account_connection_id=existing.id,
                    browser_profile_id=canonical_profile_id,
                    browser_profile_path=canonical_profile_path,
                    user_agent=existing.user_agent or session.user_agent,
                    proxy_url=session.proxy_url or existing.proxy_url,
                    connect_session_id=session.id,
                )
                merged_metadata = dict(existing.metadata_json or {})
                merged_metadata.update(
                    {
                        "connection_source": "browser_assisted",
                        "browser_connect_session_id": str(session.id),
                        "browser_profile_id": canonical_profile_id,
                        "browser_profile_path": canonical_profile_path,
                        "browser_profile_mode": "persistent_profile",
                        "last_browser_profile_open_status": summary.status,
                        "last_browser_profile_open_reason": summary.reason,
                        "last_browser_profile_open_managed_runtime_status": summary.managed_runtime_status,
                        "last_browser_profile_open_profile_conflict_status": summary.profile_conflict_status,
                        "last_browser_profile_open_purpose": "reopen_profile",
                        "last_browser_profile_open_checked_at": self._now().isoformat(),
                    }
                )
                if summary.runtime_context_id:
                    merged_metadata["browser_context_id"] = summary.runtime_context_id
                existing.metadata_json = merged_metadata
                existing.user_agent = existing.user_agent or session.user_agent
                existing.proxy_url = session.proxy_url or existing.proxy_url
                db.commit()
                db.refresh(session)
                if session.status not in RUNNING_CONNECT_STATUSES:
                    return
                session.derived_account_id = existing.id
                session.finished_at = self._now()
                session.updated_at = session.finished_at
                final_metadata = dict(session.metadata_json or {})
                final_metadata.update(
                    {
                        "browser_connect_phase": "managed_runtime_opened" if summary.status == "active" else "managed_runtime_open_failed",
                        "managed_runtime_status": summary.managed_runtime_status,
                        "managed_runtime_reason": summary.reason,
                        "runtime_context_id": summary.runtime_context_id,
                    }
                )
                session.metadata_json = final_metadata
                if summary.status == "active" and summary.runtime_context_id:
                    session.status = DouyinBrowserConnectSessionStatus.COMPLETED
                    session.last_error = None
                else:
                    session.status = DouyinBrowserConnectSessionStatus.FAILED
                    session.last_error = f"managed_runtime_unavailable:{summary.reason or summary.status}"
                db.commit()
                return

            capture = self._capture_runner.capture(
                workspace_id=session.workspace_id,
                connect_session_id=session.id,
                account_connection_id=target_account_id,
                browser_profile_id=browser_profile_id,
                browser_profile_path=browser_profile_path,
                timeout_seconds=int((session.metadata_json or {}).get("timeout_seconds", 180)),
                user_agent=session.user_agent,
                proxy_url=session.proxy_url,
                cancelled=cancelled,
                progress=progress,
            )
            if cancelled():
                return
            self._set_status(db, session, DouyinBrowserConnectSessionStatus.CAPTURING_SESSION)
            if cancelled():
                return

            account_service = DouyinAccountService(db)
            capture_metadata = dict(capture.metadata or {})
            if target_account_id:
                existing = account_service.get_account(target_account_id)
                existing_metadata = dict(existing.metadata_json or {})
                canonical_profile_id, canonical_profile_path = douyin_browser_context_registry.profile_identity_for_account(
                    existing.id,
                    browser_profile_id=existing_metadata.get("browser_profile_id") if isinstance(existing_metadata.get("browser_profile_id"), str) else None,
                    browser_profile_path=existing_metadata.get("browser_profile_path") if isinstance(existing_metadata.get("browser_profile_path"), str) else None,
                )
                if not douyin_browser_context_registry.profile_identity_matches(
                    expected_profile_id=canonical_profile_id,
                    expected_profile_path=canonical_profile_path,
                    actual_profile_id=capture.browser_profile_id,
                    actual_profile_path=capture.browser_profile_path,
                ):
                    if capture.runtime_context_id:
                        douyin_browser_context_registry.close_context(capture.runtime_context_id, reason="profile_identity_mismatch")
                    raise DouyinBrowserConnectError(
                        "profile_identity_mismatch: Refusing to bind this Douyin account to a different browser profile."
                    )
                capture_metadata["browser_profile_id"] = canonical_profile_id
                capture_metadata["browser_profile_path"] = canonical_profile_path
                capture_metadata["browser_profile_mode"] = "persistent_profile"
                capture_browser_profile_id = canonical_profile_id
                capture_browser_profile_path = canonical_profile_path
            else:
                capture_browser_profile_id = capture.browser_profile_id
                capture_browser_profile_path = capture.browser_profile_path

            profile_metadata = {
                "connection_source": "browser_assisted",
                "browser_connect_session_id": str(session.id),
                "browser_profile_id": capture_browser_profile_id,
                "browser_profile_path": capture_browser_profile_path,
                "browser_profile_mode": "persistent_profile" if capture_browser_profile_id else "ephemeral_context",
                **capture_metadata,
            }
            if target_account_id:
                merged_metadata = dict(existing.metadata_json or {})
                merged_metadata.update(profile_metadata)
                account = account_service.update_account(
                    target_account_id,
                    DouyinAccountUpdateRequest(
                        display_name=session.display_name or existing.display_name,
                        session_cookie=capture.cookie_header,
                        user_agent=capture.user_agent,
                        proxy_url=session.proxy_url,
                        is_default=session.is_default,
                        metadata_json=merged_metadata,
                    ),
                )
            else:
                account = account_service.create_account(
                    DouyinAccountCreateRequest(
                        workspace_id=session.workspace_id,
                        display_name=session.display_name or self._default_display_name(),
                        session_cookie=capture.cookie_header,
                        user_agent=capture.user_agent,
                        proxy_url=session.proxy_url,
                        is_default=session.is_default,
                        metadata_json=profile_metadata,
                    )
                )
            if capture.douyin_user_id:
                account.douyin_user_id = capture.douyin_user_id
                db.commit()
            if capture.runtime_context_id:
                douyin_browser_context_registry.bind_context(capture.runtime_context_id, account.id)

            self._set_status(db, session, DouyinBrowserConnectSessionStatus.VALIDATING)
            if cancelled():
                return
            account, valid, reason = account_service.validate_account(account.id, validation_source="connect_time")
            db.refresh(session)
            if session.status not in RUNNING_CONNECT_STATUSES:
                return
            session.derived_account_id = account.id
            metadata = dict(session.metadata_json or {})
            metadata["validation_attempt_count"] = int(metadata.get("validation_attempt_count", 0)) + 1
            session.metadata_json = metadata
            if not valid and self._should_offer_validation_retry(
                reason=reason,
                capture_status=capture.browser_prevalidation_status,
            ):
                self._mark_validation_retry_ready(
                    db=db,
                    session=session,
                    account=account,
                    reason=str(reason) + "_after_browser_prevalidation_" + str(capture.browser_prevalidation_status),
                )
                return
            session.finished_at = self._now()
            session.updated_at = session.finished_at
            if valid:
                session.status = DouyinBrowserConnectSessionStatus.COMPLETED
                session.last_error = None
            else:
                session.status = DouyinBrowserConnectSessionStatus.FAILED
                session.last_error = f"validation_failed:{reason}"
            db.commit()
        except DouyinBrowserConnectError as exc:
            self._fail_session(db, connect_session_id, str(exc))
        except Exception as exc:
            logger.exception("Douyin browser connect failed", extra={"connect_session_id": str(connect_session_id)})
            self._fail_session(db, connect_session_id, self._safe_error(str(exc)))
        finally:
            db.close()

    def _active_session_matches_target(
        self,
        session: DouyinBrowserConnectSession,
        target_account_id: UUID | None,
    ) -> bool:
        if target_account_id is None:
            return True
        if session.derived_account_id == target_account_id:
            return True
        metadata = dict(session.metadata_json or {})
        target = metadata.get("target_account_connection_id")
        return isinstance(target, str) and target == str(target_account_id)

    def _set_status(
        self,
        db: Session,
        session: DouyinBrowserConnectSession,
        status: DouyinBrowserConnectSessionStatus,
    ) -> None:
        db.refresh(session)
        if session.status not in RUNNING_CONNECT_STATUSES:
            return
        session.status = status
        session.updated_at = self._now()
        db.commit()

    def _fail_session(self, db: Session, connect_session_id: UUID, message: str) -> None:
        db.rollback()
        session = db.get(DouyinBrowserConnectSession, connect_session_id)
        if session is None or session.status not in RUNNING_CONNECT_STATUSES:
            return
        session.status = DouyinBrowserConnectSessionStatus.FAILED
        session.finished_at = self._now()
        session.updated_at = session.finished_at
        session.last_error = self._safe_error(message)
        db.commit()

    def _mark_validation_retry_ready(
        self,
        *,
        db: Session,
        session: DouyinBrowserConnectSession,
        account,
        reason: str,
    ) -> None:
        now = self._now()
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.UNKNOWN
        account.warning_level = DouyinAccountWarningLevel.INFO
        account.last_validation_status = "validation_retry_ready"
        account.last_error_code = "validation_retry_ready"
        account.last_error_message = reason
        account.warning_summary_json = {"reason": "validation_retry_ready", "last_validation_reason": reason}
        account.next_validation_due_at = now
        session.status = DouyinBrowserConnectSessionStatus.FAILED
        session.finished_at = None
        session.updated_at = now
        session.last_error = f"validation_retry_ready:{reason}"
        metadata = dict(session.metadata_json or {})
        metadata["browser_connect_phase"] = "validation_retry_ready"
        metadata["validation_retry_ready_at"] = now.isoformat()
        metadata["validation_retry_reason"] = reason
        session.metadata_json = metadata
        db.commit()

    def _should_offer_validation_retry(self, *, reason: str | None, capture_status: str | None) -> bool:
        normalized_reason = (reason or "").lower()
        normalized_capture_status = (capture_status or "").lower()
        if normalized_capture_status in {"blocked", "uncertain"}:
            return "login_required" not in normalized_reason and "expired" not in normalized_reason
        if normalized_capture_status == "passed":
            return any(
                marker in normalized_reason
                for marker in (
                    "blocked",
                    "captcha",
                    "security",
                    "verify",
                    "browser_context_blocked",
                )
            )
        return False

    def _default_display_name(self) -> str:
        return "Douyin Browser " + datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")

    def _safe_error(self, message: str, *, exc: Exception | None = None) -> str:
        if message:
            return message[:300]
        if exc is not None:
            return exc.__class__.__name__[:300]
        return "browser_connect_failed"

    def _runtime_probe(self, *, require_launch: bool) -> tuple[bool, str | None, str | None]:
        ensure_windows_playwright_event_loop_policy()
        if importlib.util.find_spec("playwright.sync_api") is None:
            return (
                False,
                "dependency_missing",
                "Playwright Python package is not installed in the API runtime. Install API dependencies, then retry.",
            )
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return (
                False,
                "dependency_missing",
                "Playwright Python package is not importable in the API runtime. Reinstall API dependencies and retry.",
            )

        try:
            with sync_playwright() as playwright:
                executable_path = playwright.chromium.executable_path
                if not executable_path or not os.path.exists(executable_path):
                    return (
                        False,
                        "browser_binary_missing",
                        "Playwright browser binary is missing. Run 'python -m playwright install chromium' in apps/api and retry.",
                    )
                if require_launch:
                    browser = None
                    try:
                        try:
                            browser = playwright.chromium.launch(channel="chrome", headless=True)
                        except Exception:
                            browser = playwright.chromium.launch(headless=True)
                    except Exception as exc:
                        code, message = playwright_runtime_error_parts("launch_failed", exc)
                        return (
                            False,
                            code,
                            message,
                        )
                    finally:
                        if browser is not None:
                            browser.close()
        except Exception as exc:
            code, message = playwright_runtime_error_parts("runtime_probe_failed", exc)
            return (
                False,
                code,
                message,
            )

        return True, None, None

    def _parse_error(self, value: str | None) -> tuple[str | None, str | None]:
        if not value:
            return None, None
        if ":" not in value:
            return value, value
        code, message = value.split(":", 1)
        return code.strip() or None, message.strip() or value

    def _next_action(self, status: str, error_code: str | None) -> str | None:
        legacy_manual_import_enabled = bool(getattr(get_settings(), "douyin_enable_legacy_manual_import", False))
        if status == DouyinBrowserConnectSessionStatus.COMPLETED.value:
            return "use_connected_account"
        if status == DouyinBrowserConnectSessionStatus.CANCELLED.value:
            return "restart_browser_connect"
        if status != DouyinBrowserConnectSessionStatus.FAILED.value:
            return "continue_in_browser"
        if error_code == "validation_retry_ready":
            return "retry_validation_or_reconnect"
        if error_code in {
            "browser_runtime_unavailable",
            "dependency_missing",
            "browser_binary_missing",
            "launch_failed",
            "runtime_probe_failed",
            "runtime_not_supported",
        }:
            return "setup_runtime_or_manual_import" if legacy_manual_import_enabled else "setup_browser_runtime"
        if error_code in {
            "login_timed_out",
            "browser_launch_timed_out",
            "session_capture_timed_out",
            "validation_timed_out",
            "overall_timed_out",
        }:
            return "retry_login_or_manual_import" if legacy_manual_import_enabled else "retry_browser_login"
        if error_code == "browser_closed":
            return "retry_login_or_manual_import" if legacy_manual_import_enabled else "reopen_browser_connect"
        if error_code == "validation_failed":
            return "manual_validate_or_reconnect"
        if error_code == "active_session_exists":
            return "cancel_running_session_or_wait"
        return "retry_or_manual_import" if legacy_manual_import_enabled else "retry_browser_connect"

    def _phase_for_status(self, status: DouyinBrowserConnectSessionStatus) -> str:
        if status in {DouyinBrowserConnectSessionStatus.PENDING, DouyinBrowserConnectSessionStatus.LAUNCHING_BROWSER}:
            return "starting_browser"
        if status == DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN:
            return "waiting_for_login"
        if status == DouyinBrowserConnectSessionStatus.CAPTURING_SESSION:
            return "capturing_session"
        if status == DouyinBrowserConnectSessionStatus.VALIDATING:
            return "validating_session"
        if status == DouyinBrowserConnectSessionStatus.COMPLETED:
            return "completed"
        if status == DouyinBrowserConnectSessionStatus.CANCELLED:
            return "cancelled"
        return "failed"

    def _phase_for_session(self, *, session: DouyinBrowserConnectSession, fallback_phase: str, error_code: str | None) -> str:
        metadata = dict(session.metadata_json or {})
        metadata_phase = metadata.get("browser_connect_phase")
        if isinstance(metadata_phase, str) and metadata_phase in {
            "login_detected",
            "stabilizing_auth",
            "validating_session",
            "validation_retry_ready",
        }:
            if session.status in RUNNING_CONNECT_STATUSES or error_code == "validation_retry_ready":
                return metadata_phase
        if error_code == "validation_retry_ready":
            return "validation_retry_ready"
        return fallback_phase

    def _outcome_for(self, *, status: DouyinBrowserConnectSessionStatus, error_code: str | None) -> str:
        if status in RUNNING_CONNECT_STATUSES:
            return "running"
        if status == DouyinBrowserConnectSessionStatus.COMPLETED:
            return "completed"
        if status == DouyinBrowserConnectSessionStatus.CANCELLED:
            return "cancelled"
        if status == DouyinBrowserConnectSessionStatus.FAILED and error_code in {
            "login_timed_out",
            "browser_launch_timed_out",
            "session_capture_timed_out",
            "validation_timed_out",
            "overall_timed_out",
        }:
            return "timed_out"
        return "failed"

    def _phase_timeout_seconds(self, phase: str, timeout_seconds: int) -> int:
        if phase == "starting_browser":
            return min(60, timeout_seconds)
        if phase == "waiting_for_login":
            return timeout_seconds
        if phase == "capturing_session":
            return 45
        if phase == "validating_session":
            return 45
        return 0

    def _phase_deadline_at(self, *, session: DouyinBrowserConnectSession, phase: str) -> datetime | None:
        phase_started_at = self._phase_started_at(session)
        if phase_started_at is None:
            return None
        timeout_seconds = int((session.metadata_json or {}).get("timeout_seconds", 180))
        budget = self._phase_timeout_seconds(phase, timeout_seconds)
        if budget <= 0:
            return None
        return self._as_aware_utc(phase_started_at) + timedelta(seconds=budget)

    def _remaining_seconds(self, phase_deadline_at: datetime | None) -> int | None:
        if phase_deadline_at is None:
            return None
        now = datetime.now(UTC)
        remaining = int((phase_deadline_at - now).total_seconds())
        return max(0, remaining)

    def _get_latest_active_looking_session(self, workspace_id: UUID) -> DouyinBrowserConnectSession | None:
        return (
            self.db.query(DouyinBrowserConnectSession)
            .filter(
                DouyinBrowserConnectSession.workspace_id == workspace_id,
                DouyinBrowserConnectSession.status.in_(tuple(RUNNING_CONNECT_STATUSES)),
            )
            .order_by(DouyinBrowserConnectSession.created_at.desc())
            .first()
        )

    def _finalize_if_stale(self, session: DouyinBrowserConnectSession) -> bool:
        is_stale, stale_reason = self._stale_state(session)
        if not is_stale:
            return False
        phase = self._phase_for_status(session.status)
        error_code = self._timeout_error_code_for_phase(phase)
        now = self._now()
        session.status = DouyinBrowserConnectSessionStatus.FAILED
        session.finished_at = now
        session.updated_at = now
        metadata = dict(session.metadata_json or {})
        metadata["stale_finalized_at"] = now.isoformat()
        metadata["stale_reason"] = stale_reason
        session.metadata_json = metadata
        session.last_error = f"{error_code}:Browser connect session became stale during {phase}."
        self.db.commit()
        self.db.refresh(session)
        logger.info(
            "Finalized stale Douyin browser connect session",
            extra={"connect_session_id": str(session.id), "phase": phase, "error_code": error_code},
        )
        return True

    def _stale_state(self, session: DouyinBrowserConnectSession) -> tuple[bool, str | None]:
        if session.status not in RUNNING_CONNECT_STATUSES:
            error_code, _ = self._parse_error(session.last_error)
            if error_code in {
                "login_timed_out",
                "browser_launch_timed_out",
                "session_capture_timed_out",
                "validation_timed_out",
                "overall_timed_out",
            }:
                return True, error_code
            return False, None
        phase = self._phase_for_status(session.status)
        deadline = self._phase_deadline_at(session=session, phase=phase)
        if deadline is None:
            return False, None
        if self._now() > deadline:
            return True, f"{phase}_deadline_expired"
        return False, None

    def _timeout_error_code_for_phase(self, phase: str) -> str:
        if phase == "starting_browser":
            return "browser_launch_timed_out"
        if phase == "waiting_for_login":
            return "login_timed_out"
        if phase == "capturing_session":
            return "session_capture_timed_out"
        if phase == "validating_session":
            return "validation_timed_out"
        return "overall_timed_out"

    def _age_seconds(self, started_at: datetime | None) -> int | None:
        if started_at is None:
            return None
        return max(0, int((self._now() - self._as_aware_utc(started_at)).total_seconds()))

    def _phase_started_at(self, session: DouyinBrowserConnectSession) -> datetime | None:
        return session.updated_at or session.started_at

    def _now(self) -> datetime:
        return datetime.now(UTC)

    def _as_aware_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def ensure_windows_playwright_event_loop_policy() -> None:
    if os.name != "nt":
        return
    policy_cls = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if policy_cls is None:
        return
    current_policy = asyncio.get_event_loop_policy()
    if isinstance(current_policy, policy_cls):
        return
    asyncio.set_event_loop_policy(policy_cls())


def playwright_runtime_error(default_code: str, exc: Exception) -> str:
    code, message = playwright_runtime_error_parts(default_code, exc)
    return f"{code}:{message}"


def playwright_runtime_error_parts(default_code: str, exc: Exception) -> tuple[str, str]:
    if isinstance(exc, NotImplementedError):
        return (
            "runtime_not_supported",
            "Playwright subprocess launch hit NotImplementedError. On Windows this usually means the API process is using an incompatible asyncio event loop policy. Restart the API after applying the Proactor runtime fix and rerun doctor.",
        )
    raw_message = str(exc).strip() or exc.__class__.__name__
    lowered = raw_message.lower()
    if "executable doesn't exist" in lowered or "please run" in lowered and "playwright install" in lowered:
        return (
            "browser_binary_missing",
            "Playwright browser binary is missing. Run 'python -m playwright install chromium' in apps/api or 'npm run playwright:install' from the repo root.",
        )
    if default_code == "browser_closed":
        return (
            "browser_closed",
            "The browser window or page closed before Douyin login completed. Retry browser connect or use manual session import.",
        )
    return (
        default_code,
        f"Playwright browser runtime failed: {raw_message[:240]}",
    )


def has_authenticated_douyin_cookies(cookies: list[dict]) -> bool:
    names = {str(cookie.get("name", "")).lower() for cookie in cookies}
    return bool(names.intersection(AUTHENTICATED_COOKIE_NAMES))


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
