from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import threading
from urllib.parse import urlparse
from uuid import UUID, uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from src.adapters.douyin import DouyinProfileAdapter
from src.adapters.douyin_live_fetch import (
    DouyinLiveFetchClient,
    DouyinLiveFetchConfig,
    HttpGet,
    extract_profile_payload_from_browser_artifacts,
)
from src.adapters.errors import SourceAdapterError, SourceAdapterErrorCode
from src.core.settings import get_settings
from src.db.bootstrap import ensure_default_workspace
from src.enums import (
    DouyinAccountConnectionStatus,
    DouyinAccountHealthStatus,
    DouyinAccountWarningLevel,
    DouyinBrowserConnectSessionStatus,
)
from src.models.source_accounts import DouyinAccountConnection, DouyinBrowserConnectSession
from src.schemas.douyin_accounts import (
    DouyinAccountCreateRequest,
    DouyinAccountDeleteResponse,
    DouyinAccountResponse,
    DouyinAccountUpdateRequest,
    DouyinBrowserHealthAlignmentSummary,
    DouyinManualImportPreflightSummary,
)
from src.services.douyin_browser_context_registry import douyin_browser_context_registry
from src.services.secret_envelope import DouyinSessionSecretEnvelope

DOUYIN_ACCOUNT_FRESH_WINDOW = timedelta(hours=24)
DOUYIN_ACCOUNT_EXPIRY_WARNING_WINDOW = timedelta(days=6)
DOUYIN_ACCOUNT_DELETE_MODE = "soft_delete"
RUNNING_BROWSER_CONNECT_STATUSES = {
    DouyinBrowserConnectSessionStatus.PENDING,
    DouyinBrowserConnectSessionStatus.LAUNCHING_BROWSER,
    DouyinBrowserConnectSessionStatus.WAITING_FOR_LOGIN,
    DouyinBrowserConnectSessionStatus.CAPTURING_SESSION,
    DouyinBrowserConnectSessionStatus.VALIDATING,
}
DOUYIN_IMPORTED_SESSION_STRONG_COOKIE_NAMES = {
    "sessionid",
    "sessionid_ss",
    "sid_guard",
    "sid_tt",
    "sid_ucp_v1",
    "uid_tt",
    "uid_tt_ss",
}
_PREFLIGHT_CACHE_LOCK = threading.RLock()
_PREFLIGHT_CACHE: dict[UUID, tuple[datetime, "DouyinFetchPreflightResult"]] = {}
DOUYIN_CHALLENGE_VALIDATION_STATUSES = {
    "browser_validation_captcha_required",
    "browser_validation_challenge_required",
    "browser_validation_manual_verification_required",
}
DOUYIN_CHALLENGE_UNRESOLVED_STATES = {
    "challenge_waiting_for_manual_verification",
    "challenge_recently_solved_pending_recheck",
    "challenge_cooldown",
    "challenge_repeat_limit_reached",
}
DOUYIN_CHALLENGE_COOLDOWN = timedelta(minutes=10)
DOUYIN_CHALLENGE_REPEAT_LIMIT = 3
DOUYIN_CHALLENGE_RECOVERY_VALIDATION_SOURCES = {"mark_challenge_solved", "challenge_recheck"}
DOUYIN_PROFILE_QUARANTINE_STATES = {
    "active_preferred",
    "active_warning",
    "quarantine_candidate",
    "quarantined",
    "quarantined_recoverable",
    "quarantined_replaced",
}
DOUYIN_PROFILE_QUARANTINE_BLOCKING_STATES = {"quarantined", "quarantined_recoverable", "quarantined_replaced"}
DOUYIN_PROFILE_QUARANTINE_CHALLENGE_THRESHOLD = DOUYIN_CHALLENGE_REPEAT_LIMIT
DOUYIN_PROFILE_QUARANTINE_BLOCKED_THRESHOLD = 3
DOUYIN_PROFILE_QUARANTINE_RECOMMENDED_ACTION = "create_clean_managed_browser_profile"
DOUYIN_OPERATOR_CONFIRMED_READY_WINDOW = timedelta(hours=6)
DOUYIN_PROFILE_QUARANTINE_RECOMMENDATION = (
    "Stop using this saved Douyin browser profile for capture or Intake. Create a fresh managed browser-backed account/profile, "
    "complete login in that clean profile, validate it, and prefer that clean profile for future Intake."
)


class DouyinAccountError(ValueError):
    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.code = code or message


@dataclass(frozen=True)
class DouyinAccountRuntimeConfig:
    account_id: UUID
    session_cookie: str
    user_agent: str
    proxy_url: str | None


@dataclass(frozen=True)
class NormalizedImportedSession:
    session_cookie: str
    user_agent: str | None
    detected_format: str
    headers_json: dict | None


@dataclass(frozen=True)
class DouyinAccountHealthSummary:
    health_status: DouyinAccountHealthStatus
    warning_level: DouyinAccountWarningLevel
    label: str
    can_use_for_live_fetch: bool
    warning_summary: dict | None
    next_validation_due_at: datetime | None
    expires_at: datetime | None


@dataclass(frozen=True)
class ManualImportPreflightResult:
    code: str
    outcome: str
    summary: str
    next_action: str
    fetch_usable: bool
    source_type: str = "manual_import"
    detected_format: str | None = None
    cookie_strength: str | None = None
    checked_at: datetime | None = None


@dataclass(frozen=True)
class DouyinChallengeRecoveryResult:
    account: DouyinAccountConnection
    valid: bool
    reason: str
    post_check_result: str
    same_profile_reused: bool
    same_runtime_reused: bool
    runtime_reopened_for_recheck: bool
    intake_ready_after_recheck: bool


@dataclass(frozen=True)
class DouyinFetchPreflightResult:
    preflight_ran: bool
    preflight_result: str
    fetch_readiness_category: str
    selected_fetch_path: str | None
    browser_profile_available: bool
    browser_reopen_attempted: bool
    browser_reopen_result: str | None = None
    browser_context_status: str | None = None
    browser_context_reason: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None
    preflight_failure_code: str | None = None
    preflight_failure_message: str | None = None
    preflight_cached: bool = False
    watchdog_result: str | None = None
    watchdog_status: str | None = None
    watchdog_reason: str | None = None
    runtime_reconciled: bool = False
    challenge_state: str | None = None
    challenge_category: str | None = None
    challenge_count: int | None = None
    challenge_cooldown_until: datetime | None = None
    challenge_recommended_next_action: str | None = None
    profile_quarantine_state: str = "active_preferred"
    profile_quarantine_reason: str | None = None
    profile_quarantine_detected: bool = False
    profile_quarantine_recommended_next_action: str | None = None
    profile_quarantine_blocks_primary_flow: bool = False
    profile_quarantine_replaced_by_account_id: UUID | None = None
    profile_quarantine_clean_profile_recommendation: str | None = None

    def to_dict(self) -> dict:
        return {
            "preflight_ran": self.preflight_ran,
            "preflight_result": self.preflight_result,
            "fetch_readiness_category": self.fetch_readiness_category,
            "selected_fetch_path": self.selected_fetch_path,
            "browser_profile_available": self.browser_profile_available,
            "browser_reopen_attempted": self.browser_reopen_attempted,
            "browser_reopen_result": self.browser_reopen_result,
            "browser_context_status": self.browser_context_status,
            "browser_context_reason": self.browser_context_reason,
            "managed_runtime_status": self.managed_runtime_status,
            "profile_conflict_status": self.profile_conflict_status,
            "preflight_failure_code": self.preflight_failure_code,
            "preflight_failure_message": self.preflight_failure_message,
            "preflight_cached": self.preflight_cached,
            "watchdog_result": self.watchdog_result,
            "watchdog_status": self.watchdog_status,
            "watchdog_reason": self.watchdog_reason,
            "runtime_reconciled": self.runtime_reconciled,
            "challenge_state": self.challenge_state,
            "challenge_category": self.challenge_category,
            "challenge_count": self.challenge_count,
            "challenge_cooldown_until": self.challenge_cooldown_until,
            "challenge_recommended_next_action": self.challenge_recommended_next_action,
            "profile_quarantine_state": self.profile_quarantine_state,
            "profile_quarantine_reason": self.profile_quarantine_reason,
            "profile_quarantine_detected": self.profile_quarantine_detected,
            "profile_quarantine_recommended_next_action": self.profile_quarantine_recommended_next_action,
            "profile_quarantine_blocks_primary_flow": self.profile_quarantine_blocks_primary_flow,
            "profile_quarantine_replaced_by_account_id": self.profile_quarantine_replaced_by_account_id,
            "profile_quarantine_clean_profile_recommendation": self.profile_quarantine_clean_profile_recommendation,
        }


@dataclass(frozen=True)
class DouyinAccountReadinessRow:
    account_id: UUID
    display_name: str
    is_default: bool
    status: DouyinAccountConnectionStatus
    health_status: DouyinAccountHealthStatus
    soft_deleted: bool
    has_browser_profile: bool
    browser_profile_id: str | None
    browser_profile_path: str | None
    profile_path_exists: bool
    browser_context_status: str | None
    readiness_status: str
    blocking_reason: str | None
    preflight_ran: bool
    preflight_result: str | None
    preflight_failure_code: str | None
    selected_fetch_path: str | None

    def to_dict(self) -> dict:
        return {
            "account_id": str(self.account_id),
            "display_name": self.display_name,
            "is_default": self.is_default,
            "status": self.status.value,
            "health_status": self.health_status.value,
            "soft_deleted": self.soft_deleted,
            "has_browser_profile": self.has_browser_profile,
            "browser_profile_id": self.browser_profile_id,
            "browser_profile_path": self.browser_profile_path,
            "profile_path_exists": self.profile_path_exists,
            "browser_context_status": self.browser_context_status,
            "readiness_status": self.readiness_status,
            "blocking_reason": self.blocking_reason,
            "preflight_ran": self.preflight_ran,
            "preflight_result": self.preflight_result,
            "preflight_failure_code": self.preflight_failure_code,
            "selected_fetch_path": self.selected_fetch_path,
        }


class DouyinAccountService:
    def __init__(self, db: Session, *, http_get: HttpGet | None = None):
        self.db = db
        self._http_get = http_get

    def _legacy_manual_import_enabled(self) -> bool:
        return bool(getattr(get_settings(), "douyin_enable_legacy_manual_import", False))

    def _legacy_http_fallback_enabled(self) -> bool:
        return bool(getattr(get_settings(), "douyin_enable_legacy_http_fallback", False))

    def _legacy_debug_surfaces_enabled(self) -> bool:
        return bool(getattr(get_settings(), "douyin_enable_legacy_debug_surfaces", False))

    def invalidate_preflight_cache(self, account_id: UUID) -> None:
        with _PREFLIGHT_CACHE_LOCK:
            _PREFLIGHT_CACHE.pop(account_id, None)

    def _cached_preflight_result(self, account_id: UUID) -> DouyinFetchPreflightResult | None:
        settings = get_settings()
        ttl_seconds = max(0, int(getattr(settings, "douyin_intake_preflight_cache_ttl_seconds", 30)))
        if ttl_seconds <= 0:
            return None
        now = datetime.now(UTC)
        with _PREFLIGHT_CACHE_LOCK:
            cached = _PREFLIGHT_CACHE.get(account_id)
            if cached is None:
                return None
            stored_at, result = cached
            if (now - stored_at).total_seconds() > ttl_seconds:
                _PREFLIGHT_CACHE.pop(account_id, None)
                return None
        return replace(
            result,
            preflight_cached=True,
            browser_reopen_attempted=False,
            browser_reopen_result="cache_hit",
        )

    def _store_preflight_result(self, account_id: UUID, result: DouyinFetchPreflightResult) -> DouyinFetchPreflightResult:
        if result.preflight_result != "passed":
            self.invalidate_preflight_cache(account_id)
            return result
        with _PREFLIGHT_CACHE_LOCK:
            _PREFLIGHT_CACHE[account_id] = (datetime.now(UTC), replace(result, preflight_cached=False))
        return result

    def create_account(self, request: DouyinAccountCreateRequest) -> DouyinAccountConnection:
        workspace_id = request.workspace_id or ensure_default_workspace(self.db).id
        metadata_json = dict(request.metadata_json or {})
        normalized_import = self._normalize_imported_session(
            request.session_cookie,
            explicit_user_agent=request.user_agent,
            headers_json=request.headers_json,
            require_user_agent=self._is_manual_import_metadata(metadata_json),
            enforce_cookie_strength=self._is_manual_import_metadata(metadata_json),
        )
        metadata_json.setdefault("session_runtime_shape", "cookie_header_v1")
        metadata_json.setdefault("session_import_format", normalized_import.detected_format)
        account = DouyinAccountConnection(
            workspace_id=workspace_id,
            display_name=request.display_name,
            status=DouyinAccountConnectionStatus.INVALID,
            health_status=DouyinAccountHealthStatus.UNKNOWN,
            warning_level=DouyinAccountWarningLevel.INFO,
            is_default=request.is_default,
            session_secret_blob=self._encode_session_cookie(normalized_import.session_cookie),
            user_agent=normalized_import.user_agent,
            proxy_url=request.proxy_url,
            headers_json=normalized_import.headers_json,
            metadata_json=metadata_json,
            notes=request.notes,
            next_validation_due_at=datetime.now(UTC),
            warning_summary_json={"reason": "not_validated"},
        )
        if request.is_default:
            self._clear_default(workspace_id)
        self.db.add(account)
        self.db.commit()
        self.db.refresh(account)
        self.invalidate_preflight_cache(account.id)
        if self._legacy_manual_import_enabled() and self._is_manual_import_account(account):
            account, _, _ = self.validate_account(account.id, validation_source="manual_import_smoke")
        return account

    def list_accounts(
        self,
        *,
        workspace_id: UUID | None = None,
        status: DouyinAccountConnectionStatus | None = None,
        include_deleted: bool = False,
    ) -> list[DouyinAccountConnection]:
        stmt = select(DouyinAccountConnection).order_by(
            DouyinAccountConnection.is_default.desc(),
            DouyinAccountConnection.updated_at.desc(),
        )
        if workspace_id is not None:
            stmt = stmt.where(DouyinAccountConnection.workspace_id == workspace_id)
        if status is not None:
            stmt = stmt.where(DouyinAccountConnection.status == status)
        accounts = list(self.db.scalars(stmt))
        if include_deleted:
            return accounts
        return [account for account in accounts if not self._is_soft_deleted(account)]

    def get_account(self, account_id: UUID) -> DouyinAccountConnection:
        account = self.db.get(DouyinAccountConnection, account_id)
        if account is None:
            raise DouyinAccountError("Douyin account connection not found")
        return account

    def default_account(self, *, workspace_id: UUID | None = None) -> DouyinAccountConnection | None:
        stmt = select(DouyinAccountConnection).where(DouyinAccountConnection.is_default.is_(True))
        if workspace_id is not None:
            stmt = stmt.where(DouyinAccountConnection.workspace_id == workspace_id)
        return self.db.scalar(stmt.order_by(DouyinAccountConnection.updated_at.desc()).limit(1))

    def create_browser_profile_account(
        self,
        *,
        display_name: str,
        workspace_id: UUID | None = None,
        browser_profile_path: str | None = None,
        browser_profile_id: str | None = None,
        user_agent: str | None = None,
        proxy_url: str | None = None,
        is_default: bool = False,
        notes: str | None = None,
    ) -> DouyinAccountConnection:
        resolved_workspace_id = workspace_id or ensure_default_workspace(self.db).id
        account = DouyinAccountConnection(
            workspace_id=resolved_workspace_id,
            display_name=display_name.strip(),
            status=DouyinAccountConnectionStatus.INVALID,
            health_status=DouyinAccountHealthStatus.UNKNOWN,
            warning_level=DouyinAccountWarningLevel.INFO,
            is_default=False,
            session_secret_blob=None,
            user_agent=user_agent,
            proxy_url=proxy_url,
            headers_json=None,
            metadata_json={"connection_source": "browser_profile"},
            notes=notes,
            next_validation_due_at=datetime.now(UTC),
            warning_summary_json={"reason": "not_validated"},
        )
        self.db.add(account)
        self.db.flush()
        metadata = dict(account.metadata_json or {})
        resolved_profile_id, resolved_profile_path = douyin_browser_context_registry.profile_identity_for_account(
            account.id,
            browser_profile_id=browser_profile_id,
            browser_profile_path=browser_profile_path,
        )
        metadata["browser_profile_id"] = resolved_profile_id
        metadata["browser_profile_path"] = resolved_profile_path
        metadata["browser_profile_mode"] = "persistent_profile"
        account.metadata_json = metadata
        if is_default:
            self._clear_default(account.workspace_id)
            account.is_default = True
        self._apply_health_projection(account)
        self.db.commit()
        self.db.refresh(account)
        self.invalidate_preflight_cache(account.id)
        return account

    def attach_browser_profile(
        self,
        account_id: UUID,
        *,
        browser_profile_path: str,
        browser_profile_id: str | None = None,
    ) -> DouyinAccountConnection:
        account = self.get_account(account_id)
        if self._is_soft_deleted(account):
            raise DouyinAccountError(
                "Cannot attach a browser profile to a deleted Douyin account. Create a fresh browser-backed account instead.",
                code="deleted_account_cannot_attach_profile",
            )
        metadata = dict(getattr(account, "metadata_json", None) or {})
        resolved_profile_id, resolved_profile_path = douyin_browser_context_registry.profile_identity_for_account(
            account.id,
            browser_profile_id=browser_profile_id,
            browser_profile_path=browser_profile_path,
        )
        metadata["browser_profile_id"] = resolved_profile_id
        metadata["browser_profile_path"] = resolved_profile_path
        metadata["browser_profile_mode"] = "persistent_profile"
        account.metadata_json = metadata
        account.next_validation_due_at = datetime.now(UTC)
        self._apply_health_projection(account)
        self.db.commit()
        self.db.refresh(account)
        self.invalidate_preflight_cache(account.id)
        return account

    def set_default_account(self, account_id: UUID) -> DouyinAccountConnection:
        account = self.get_account(account_id)
        if self._is_soft_deleted(account):
            raise DouyinAccountError(
                "Cannot set a deleted Douyin account as default.",
                code="deleted_account_cannot_be_default",
            )
        self._clear_default(account.workspace_id)
        account.is_default = True
        self.db.commit()
        self.db.refresh(account)
        return account

    def readiness_rows(
        self,
        *,
        workspace_id: UUID | None = None,
        include_deleted: bool = False,
        run_preflight: bool = True,
    ) -> list[DouyinAccountReadinessRow]:
        accounts = self.list_accounts(workspace_id=workspace_id, include_deleted=include_deleted)
        rows: list[DouyinAccountReadinessRow] = []
        for account in accounts:
            metadata = dict(getattr(account, "metadata_json", None) or {})
            browser_profile_id = metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None
            browser_profile_path = metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None
            has_browser_profile = bool(browser_profile_id or browser_profile_path)
            profile_path_exists = bool(browser_profile_path and Path(browser_profile_path).exists())
            soft_deleted = self._is_soft_deleted(account)
            browser_context = douyin_browser_context_registry.summary_for_account(account.id)
            preflight = None
            if run_preflight and not soft_deleted:
                try:
                    preflight = self.preflight_fetch_readiness(account.id)
                except Exception as exc:  # noqa: BLE001
                    rows.append(
                        DouyinAccountReadinessRow(
                            account_id=account.id,
                            display_name=account.display_name,
                            is_default=bool(account.is_default),
                            status=account.status,
                            health_status=self.health_summary(account).health_status,
                            soft_deleted=soft_deleted,
                            has_browser_profile=has_browser_profile,
                            browser_profile_id=browser_profile_id,
                            browser_profile_path=browser_profile_path,
                            profile_path_exists=profile_path_exists,
                            browser_context_status=browser_context.status,
                            readiness_status="ERROR",
                            blocking_reason=f"readiness_probe_failed:{exc.__class__.__name__}",
                            preflight_ran=True,
                            preflight_result="error",
                            preflight_failure_code="readiness_probe_failed",
                            selected_fetch_path=None,
                        )
                    )
                    continue
            if soft_deleted:
                readiness_status = "DELETED"
                blocking_reason = "soft_deleted"
            elif not has_browser_profile:
                readiness_status = "NOT_READY"
                blocking_reason = "browser_profile_missing"
            elif not profile_path_exists:
                readiness_status = "NOT_READY"
                blocking_reason = "browser_profile_path_missing"
            elif preflight is not None and preflight.preflight_result == "passed" and preflight.selected_fetch_path == "browser_profile":
                readiness_status = "OPERATOR_CONFIRMED" if preflight.fetch_readiness_category == "fetch_ready_operator_confirmed" else "READY"
                blocking_reason = None
            elif preflight is not None:
                readiness_status = "NOT_READY"
                blocking_reason = preflight.preflight_failure_code or preflight.preflight_failure_message
                if blocking_reason == "account_not_fetch_ready":
                    blocking_reason = (
                        getattr(account, "last_error_code", None)
                        or getattr(account, "last_validation_status", None)
                        or (
                            "manual_revalidation_required"
                            if has_browser_profile and account.health_status == DouyinAccountHealthStatus.UNKNOWN
                            else "account_not_fetch_ready"
                        )
                    )
            else:
                readiness_status = "PROFILE_ATTACHED"
                blocking_reason = None
            rows.append(
                DouyinAccountReadinessRow(
                    account_id=account.id,
                    display_name=account.display_name,
                    is_default=bool(account.is_default),
                    status=account.status,
                    health_status=self.health_summary(account).health_status,
                    soft_deleted=soft_deleted,
                    has_browser_profile=has_browser_profile,
                    browser_profile_id=browser_profile_id,
                    browser_profile_path=browser_profile_path,
                    profile_path_exists=profile_path_exists,
                    browser_context_status=browser_context.status,
                    readiness_status=readiness_status,
                    blocking_reason=blocking_reason,
                    preflight_ran=preflight is not None,
                    preflight_result=preflight.preflight_result if preflight is not None else None,
                    preflight_failure_code=preflight.preflight_failure_code if preflight is not None else None,
                    selected_fetch_path=preflight.selected_fetch_path if preflight is not None else None,
                )
            )
        return rows

    def update_account(self, account_id: UUID, request: DouyinAccountUpdateRequest) -> DouyinAccountConnection:
        account = self.get_account(account_id)
        provided = request.model_fields_set
        incoming_metadata = request.metadata_json if "metadata_json" in provided else account.metadata_json
        next_metadata_json = dict(incoming_metadata or {})
        should_revalidate_manual_import = False
        next_headers_json = request.headers_json if "headers_json" in provided else account.headers_json
        if "display_name" in provided and request.display_name is not None:
            account.display_name = request.display_name
        if self._is_manual_import_metadata(next_metadata_json) and {"session_cookie", "user_agent", "headers_json"} & provided:
            raw_session_input = request.session_cookie if "session_cookie" in provided else self._decode_session_cookie(account.session_secret_blob)
            normalized_import = self._normalize_imported_session(
                raw_session_input,
                explicit_user_agent=request.user_agent if "user_agent" in provided else account.user_agent,
                headers_json=next_headers_json,
                require_user_agent=True,
                enforce_cookie_strength=True,
            )
            account.session_secret_blob = self._encode_session_cookie(normalized_import.session_cookie)
            account.user_agent = normalized_import.user_agent
            account.headers_json = normalized_import.headers_json
            next_metadata_json["session_runtime_shape"] = "cookie_header_v1"
            next_metadata_json["session_import_format"] = normalized_import.detected_format
            account.status = DouyinAccountConnectionStatus.INVALID
            account.last_validation_status = "session_updated_requires_validation"
            account.validation_source = "session_update"
            account.last_error_code = None
            account.last_error_message = None
            account.last_successful_validation_at = None
            account.next_validation_due_at = datetime.now(UTC)
            self._apply_health_projection(account)
            should_revalidate_manual_import = True
        elif "session_cookie" in provided and request.session_cookie is not None:
            normalized_session_cookie = self._normalize_session_cookie_input(
                request.session_cookie,
                headers_json=next_headers_json,
            )
            account.session_secret_blob = self._encode_session_cookie(normalized_session_cookie)
            account.status = DouyinAccountConnectionStatus.INVALID
            account.last_validation_status = "session_updated_requires_validation"
            account.validation_source = "session_update"
            account.last_error_code = None
            account.last_error_message = None
            account.last_successful_validation_at = None
            account.next_validation_due_at = datetime.now(UTC)
            self._apply_health_projection(account)
        for field in ["user_agent", "proxy_url", "headers_json", "metadata_json", "notes"]:
            if field in provided:
                if field == "metadata_json":
                    account.metadata_json = next_metadata_json
                elif not (field in {"user_agent", "headers_json"} and self._is_manual_import_metadata(next_metadata_json)):
                    setattr(account, field, getattr(request, field))
        if "status" in provided and request.status is not None:
            account.status = request.status
            self._apply_health_projection(account)
        if "is_default" in provided and request.is_default is not None:
            if request.is_default:
                self._clear_default(account.workspace_id)
            account.is_default = request.is_default
        self.db.commit()
        self.db.refresh(account)
        self.invalidate_preflight_cache(account.id)
        if should_revalidate_manual_import and self._legacy_manual_import_enabled():
            account, _, _ = self.validate_account(account.id, validation_source="manual_import_smoke")
        return account

    def delete_account(self, account_id: UUID) -> DouyinAccountDeleteResponse:
        account = self.get_account(account_id)
        if self._has_active_browser_connect_session(account.id):
            raise DouyinAccountError("account_delete_blocked_active_browser_connect_session")

        warnings: list[str] = []
        health = self.health_summary(account)
        usable_accounts = [
            item
            for item in self.list_accounts(workspace_id=account.workspace_id)
            if item.id != account.id and self.health_summary(item).can_use_for_live_fetch
        ]

        if account.is_default:
            warnings.append("deleted_account_was_default")
        if health.can_use_for_live_fetch:
            warnings.append("deleted_account_was_usable_for_live_fetch")
        if health.can_use_for_live_fetch and not usable_accounts:
            warnings.append("deleted_account_was_only_usable_live_fetch_account")

        now = datetime.now(UTC)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        metadata.setdefault("original_display_name", account.display_name)
        metadata["delete_mode"] = DOUYIN_ACCOUNT_DELETE_MODE
        metadata["deleted_at"] = now.isoformat()
        metadata["deleted_reason"] = "operator_delete"
        account.metadata_json = metadata
        account.display_name = self._deleted_display_name(account.display_name, account.id, now)
        account.status = DouyinAccountConnectionStatus.DISABLED
        account.is_default = False
        account.last_error_code = None
        account.last_error_message = None
        account.validation_source = "operator_delete"
        account.last_validation_status = "soft_deleted"
        self._apply_health_projection(account, now=now)
        douyin_browser_context_registry.close_for_account(account.id, reason="account_deleted")
        self.invalidate_preflight_cache(account.id)
        self.db.commit()
        return DouyinAccountDeleteResponse(
            deleted_account_id=account.id,
            delete_mode=DOUYIN_ACCOUNT_DELETE_MODE,
            success=True,
            warnings=warnings,
            recommended_follow_up="Select or validate another Douyin account in /intake before running live fetch."
            if "deleted_account_was_only_usable_live_fetch_account" in warnings
            else None,
        )

    def disable_account(self, account_id: UUID) -> DouyinAccountConnection:
        account = self.get_account(account_id)
        account.status = DouyinAccountConnectionStatus.DISABLED
        account.is_default = False
        self._apply_health_projection(account)
        douyin_browser_context_registry.close_for_account(account.id, reason="account_disabled")
        self.invalidate_preflight_cache(account.id)
        self.db.commit()
        self.db.refresh(account)
        return account

    def validate_account(
        self,
        account_id: UUID,
        *,
        validation_url: str | None = None,
        validation_source: str = "manual_validate",
    ) -> tuple[DouyinAccountConnection, bool, str]:
        account = self.get_account(account_id)
        self.invalidate_preflight_cache(account_id)
        reason = "validated"
        valid = False
        status = DouyinAccountConnectionStatus.INVALID
        now = datetime.now(UTC)
        account.last_validated_at = now
        account.validation_source = validation_source
        metadata = dict(getattr(account, "metadata_json", None) or {})
        cooldown_active, cooldown_state, cooldown_until = self._active_challenge_cooldown(metadata, now=now)
        if cooldown_active and validation_source not in DOUYIN_CHALLENGE_RECOVERY_VALIDATION_SOURCES:
            metadata["last_browser_validation_category"] = "challenge_cooldown_active"
            metadata["last_browser_validation_final_category"] = "challenge_cooldown_active"
            metadata["last_browser_validation_challenge_category"] = metadata.get("douyin_challenge_category")
            metadata["last_browser_validation_recommended_next_action"] = "wait_or_mark_challenge_solved_after_manual_completion"
            metadata["douyin_challenge_recommended_next_action"] = "wait_or_mark_challenge_solved_after_manual_completion"
            account.metadata_json = metadata
            account.status = DouyinAccountConnectionStatus.BLOCKED
            account.last_validation_status = "challenge_cooldown_active"
            account.last_error_code = "challenge_cooldown_active"
            account.last_error_message = (
                f"Douyin challenge cooldown is active until {cooldown_until.isoformat()} after {cooldown_state}. "
                "Complete the challenge in the saved browser profile, then use Mark challenge solved for the post-challenge recheck."
            )
            self._apply_health_projection(account, now=now)
            self.db.commit()
            self.db.refresh(account)
            return account, False, "challenge_cooldown_active"

        try:
            context_result = self._validate_with_live_browser_context(
                account=account,
                validation_url=validation_url,
                now=now,
                validation_source=validation_source,
            )
            if context_result is not None:
                valid, browser_reason = context_result
                self.db.commit()
                self.db.refresh(account)
                return account, valid, browser_reason
            settings = get_settings()
            if not self._legacy_http_fallback_enabled():
                status = DouyinAccountConnectionStatus.INVALID
                reason = "browser_profile_required"
                account.status = status
                account.last_validation_status = reason
                account.last_error_code = reason
                account.last_error_message = (
                    "Browser-profile-backed validation is required. Legacy detached HTTP validation fallback is disabled."
                )
                account.next_validation_due_at = now
                self._apply_health_projection(account, now=now)
                self.db.commit()
                self.db.refresh(account)
                return account, False, reason
            runtime = self.resolve_runtime_config(account_id, require_active=False)
            client = self.build_fetch_client(runtime)
            target_url = self._safe_validation_url(validation_url)
            html = client.fetch_html(target_url)
            lowered = html.lower()
            if any(marker in lowered for marker in ("captcha", "verify", "blocked", "security check")):
                status = DouyinAccountConnectionStatus.BLOCKED
                reason = "blocked_response"
            elif any(marker in lowered for marker in ("login", "passport", "not login", "未登录", "æœªç™»å½•")):
                status = DouyinAccountConnectionStatus.EXPIRED
                reason = "expired_or_login_required"
            elif not self._looks_like_douyin_preflight_html(lowered):
                status = DouyinAccountConnectionStatus.INVALID
                reason = "validation_parse_failed"
            else:
                status = DouyinAccountConnectionStatus.ACTIVE
                reason = "session_reachable"
                valid = True
                account.last_successful_validation_at = now
            account.last_error_message = None if valid else reason
            account.last_error_code = None if valid else self._normalize_validation_status(reason)
        except DouyinAccountError as exc:
            reason = getattr(exc, "code", None) or str(exc)
            account.last_error_code = getattr(exc, "code", None) or self._normalize_validation_status(str(exc))
            account.last_error_message = str(exc)
        except SourceAdapterError as exc:
            status = self._status_from_adapter_error(exc)
            reason = str(exc.code)
            account.last_error_code = self._classify_validation_adapter_error(exc)
            account.last_error_message = exc.message

        account.status = status
        account.last_validation_status = reason
        self._update_manual_import_preflight(
            account,
            code=self._manual_import_preflight_code_for_account(account, valid=valid),
            checked_at=now,
        )
        self._apply_health_projection(account, now=now)
        self.db.commit()
        self.db.refresh(account)
        return account, valid, reason

    def mark_challenge_solved(self, account_id: UUID, *, validation_url: str | None = None) -> DouyinChallengeRecoveryResult:
        return self._run_challenge_recovery(
            account_id,
            validation_url=validation_url,
            require_pending_recheck=False,
            action_source="mark_challenge_solved",
        )

    def recheck_challenge_after_solve(self, account_id: UUID, *, validation_url: str | None = None) -> DouyinChallengeRecoveryResult:
        return self._run_challenge_recovery(
            account_id,
            validation_url=validation_url,
            require_pending_recheck=True,
            action_source="challenge_recheck",
        )

    def clear_challenge_state_for_revalidation(self, account_id: UUID) -> DouyinAccountConnection:
        account = self.get_account(account_id)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        if not self._has_saved_browser_profile_metadata(metadata):
            raise DouyinAccountError(
                "Douyin challenge clear requires a saved reusable browser profile.",
                code="browser_profile_required",
            )
        if not self._is_challenge_actionable(metadata, account.last_validation_status) and self._effective_challenge_state(
            metadata,
            now=datetime.now(UTC),
        ) != "challenge_cooldown_active":
            raise DouyinAccountError(
                "No stale Douyin challenge/cooldown state is waiting to be cleared.",
                code="challenge_state_not_present",
            )

        now = datetime.now(UTC)
        self._clear_challenge_metadata(metadata)
        metadata.pop("browser_context_blocked_count", None)
        metadata.pop("douyin_profile_quarantine_state", None)
        metadata.pop("douyin_profile_quarantine_reason", None)
        metadata.pop("douyin_profile_quarantine_detected_at", None)
        metadata.pop("douyin_profile_quarantine_recommended_next_action", None)
        metadata["manual_challenge_clear_at"] = now.isoformat()
        metadata["manual_challenge_clear_source"] = "operator_command"
        metadata["manual_challenge_clear_requires_revalidate"] = True
        account.metadata_json = metadata
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.UNKNOWN
        account.warning_level = DouyinAccountWarningLevel.INFO
        account.last_validation_status = "manual_revalidation_required"
        account.last_error_code = "manual_revalidation_required"
        account.last_error_message = (
            "Operator manually confirmed the saved browser profile can access Douyin. Run browser-backed revalidate before hydration or Intake."
        )
        account.last_validated_at = None
        account.last_successful_validation_at = None
        account.next_validation_due_at = now
        account.expires_at = None
        account.warning_summary_json = {"reason": "manual_revalidation_required"}
        self.invalidate_preflight_cache(account.id)
        self.db.commit()
        self.db.refresh(account)
        return account

    def operator_confirm_ready(self, account_id: UUID) -> DouyinAccountConnection:
        account = self.get_account(account_id)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        if not self._has_saved_browser_profile_metadata(metadata):
            raise DouyinAccountError(
                "Douyin operator-confirm-ready requires a saved reusable browser profile.",
                code="browser_profile_required",
            )

        now = datetime.now(UTC)
        self._clear_challenge_metadata(metadata)
        for key in (
            "browser_context_blocked_count",
            "douyin_profile_quarantine_state",
            "douyin_profile_quarantine_reason",
            "douyin_profile_quarantine_detected_at",
            "douyin_profile_quarantine_recommended_next_action",
            "last_browser_context_status",
            "last_browser_context_reason",
            "last_browser_validation_category",
            "last_browser_validation_final_category",
            "last_browser_validation_blocked_probe_reason",
            "last_browser_validation_challenge_category",
            "last_browser_validation_recommended_next_action",
        ):
            metadata.pop(key, None)
        metadata["operator_confirmed_ready_at"] = now.isoformat()
        metadata["operator_confirmed_ready_source"] = "operator_command"
        metadata["operator_confirmed_ready_warning"] = "Manual confirmation only. Hydration may still hit captcha."
        account.metadata_json = metadata
        account.status = DouyinAccountConnectionStatus.INVALID
        account.health_status = DouyinAccountHealthStatus.UNKNOWN
        account.warning_level = DouyinAccountWarningLevel.WARN
        account.last_validation_status = "operator_confirmed_ready"
        account.last_error_code = "operator_confirmed_ready"
        account.last_error_message = (
            "Operator manually confirmed that the saved browser profile can access Douyin. "
            "Hydration may proceed for a limited window, but browser-backed revalidate remains stronger evidence."
        )
        account.last_validated_at = now
        account.next_validation_due_at = now + DOUYIN_OPERATOR_CONFIRMED_READY_WINDOW
        account.warning_summary_json = {"reason": "operator_confirmed_ready"}
        self.invalidate_preflight_cache(account.id)
        self.db.commit()
        self.db.refresh(account)
        return account

    def _run_challenge_recovery(
        self,
        account_id: UUID,
        *,
        validation_url: str | None,
        require_pending_recheck: bool,
        action_source: str,
    ) -> DouyinChallengeRecoveryResult:
        account = self.get_account(account_id)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        if not self._has_saved_browser_profile_metadata(metadata):
            raise DouyinAccountError(
                "Douyin challenge solve requires a saved reusable browser profile.",
                code="browser_profile_required",
            )
        if require_pending_recheck:
            if metadata.get("douyin_challenge_state") != "challenge_recently_solved_pending_recheck":
                raise DouyinAccountError(
                    "Mark the Douyin challenge solved before running the post-solve recheck.",
                    code="challenge_recheck_not_pending",
                )
        elif not self._is_challenge_actionable(metadata, account.last_validation_status):
            raise DouyinAccountError(
                "No actionable Douyin browser challenge is waiting for manual verification.",
                code="challenge_not_waiting_for_manual_verification",
            )

        attempt_id = str(uuid4())
        now = datetime.now(UTC)
        runtime_before_summary = douyin_browser_context_registry.summary_for_account(account.id)
        profile_before_id, profile_before_path = self._saved_profile_identity(metadata, account.id)
        metadata["douyin_challenge_state"] = "challenge_recently_solved_pending_recheck"
        metadata["douyin_challenge_last_solved_at"] = now.isoformat()
        metadata["douyin_challenge_mark_solved_attempted"] = True
        metadata["douyin_challenge_mark_solved_attempted_at"] = now.isoformat()
        metadata["douyin_challenge_recheck_attempt_id"] = attempt_id
        metadata["douyin_challenge_recheck_started_at"] = now.isoformat()
        metadata["douyin_challenge_recheck_resolved"] = False
        metadata["douyin_challenge_same_runtime_reused"] = False
        metadata["douyin_challenge_same_profile_reused"] = False
        metadata["douyin_challenge_runtime_reopened_for_recheck"] = False
        metadata["douyin_challenge_intake_ready_after_recheck"] = False
        metadata["douyin_challenge_postcheck_result"] = "challenge_postcheck_inconclusive"
        metadata["douyin_challenge_recommended_next_action"] = "running_browser_validation_after_manual_solve"
        account.metadata_json = metadata
        account.last_validation_status = "challenge_recently_solved_pending_recheck"
        account.last_error_code = "challenge_recheck_required"
        account.last_error_message = "Operator marked the Douyin challenge solved; browser-backed validation is running in the saved profile."
        self._apply_health_projection(account, now=now)
        self.invalidate_preflight_cache(account.id)
        self.db.commit()

        account, valid, reason = self.validate_account(
            account.id,
            validation_url=validation_url,
            validation_source=action_source,
        )
        metadata = dict(getattr(account, "metadata_json", None) or {})
        runtime_after_summary = douyin_browser_context_registry.summary_for_account(account.id)
        profile_after_id, profile_after_path = self._saved_profile_identity(metadata, account.id)
        same_runtime_reused = bool(
            runtime_before_summary.runtime_context_id
            and runtime_after_summary.runtime_context_id
            and runtime_before_summary.runtime_context_id == runtime_after_summary.runtime_context_id
        )
        same_profile_reused = douyin_browser_context_registry.profile_identity_matches(
            expected_profile_id=profile_before_id,
            expected_profile_path=profile_before_path,
            actual_profile_id=profile_after_id,
            actual_profile_path=profile_after_path,
        )
        runtime_reopened = bool(metadata.get("last_browser_validation_runtime_reattached")) or (
            metadata.get("last_browser_validation_reopen_status") == "browser_validation_runtime_reopened"
        )
        post_check_result = self._challenge_postcheck_result_for(reason=reason, valid=valid)
        if post_check_result == "challenge_postcheck_success" and not same_profile_reused:
            post_check_result = "challenge_postcheck_profile_mismatch"
            valid = False
            reason = "runtime_rebind_profile_mismatch"
            account.status = DouyinAccountConnectionStatus.INVALID
            account.last_validation_status = "runtime_rebind_profile_mismatch"
            account.last_error_code = "browser_validation_profile_mismatch"
            account.last_error_message = "Post-challenge validation did not prove reuse of the saved browser profile. Reopen the saved profile from this app and retry."
        intake_ready_after_recheck = bool(valid and reason == "browser_validation_success" and same_profile_reused)

        if post_check_result == "challenge_postcheck_success":
            self._clear_challenge_metadata(metadata)
            metadata["douyin_challenge_recheck_resolved"] = True
        else:
            metadata["douyin_challenge_recheck_resolved"] = False
            next_action = self._challenge_next_action_for_postcheck(post_check_result)
            if post_check_result == "challenge_postcheck_still_required" and metadata.get("douyin_challenge_state") == "challenge_recently_solved_pending_recheck":
                category, challenge_category, recommended_next_action = self._classify_browser_validation_challenge(account.last_error_message or reason)
                _, next_action = self._set_challenge_detected_metadata(
                    metadata,
                    now=datetime.now(UTC),
                    category=category,
                    challenge_category=challenge_category,
                    recommended_next_action=recommended_next_action,
                )
            elif metadata.get("douyin_challenge_state") == "challenge_recently_solved_pending_recheck":
                metadata["douyin_challenge_state"] = "challenge_waiting_for_manual_verification"
                metadata["douyin_challenge_recommended_next_action"] = next_action
            else:
                metadata["douyin_challenge_recommended_next_action"] = next_action

        metadata["douyin_challenge_mark_solved_attempted"] = True
        metadata["douyin_challenge_recheck_attempt_id"] = attempt_id
        metadata["douyin_challenge_recheck_started_at"] = now.isoformat()
        metadata["douyin_challenge_postcheck_result"] = post_check_result
        metadata["douyin_challenge_same_runtime_reused"] = same_runtime_reused
        metadata["douyin_challenge_same_profile_reused"] = same_profile_reused
        metadata["douyin_challenge_runtime_reopened_for_recheck"] = runtime_reopened
        metadata["douyin_challenge_intake_ready_after_recheck"] = intake_ready_after_recheck
        account.metadata_json = metadata
        self._apply_health_projection(account, now=datetime.now(UTC))
        self.invalidate_preflight_cache(account.id)
        self.db.commit()
        self.db.refresh(account)
        return DouyinChallengeRecoveryResult(
            account=account,
            valid=valid,
            reason=reason,
            post_check_result=post_check_result,
            same_profile_reused=same_profile_reused,
            same_runtime_reused=same_runtime_reused,
            runtime_reopened_for_recheck=runtime_reopened,
            intake_ready_after_recheck=intake_ready_after_recheck,
        )

    def health_summary(self, account: DouyinAccountConnection, *, now: datetime | None = None) -> DouyinAccountHealthSummary:
        now = now or datetime.now(UTC)
        next_due = account.next_validation_due_at
        expires_at = account.expires_at

        if account.status == DouyinAccountConnectionStatus.DISABLED:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.DISABLED,
                DouyinAccountWarningLevel.BLOCK,
                "Disabled",
                False,
                {"reason": "operator_disabled"},
                next_due,
                expires_at,
            )
        metadata = dict(getattr(account, "metadata_json", None) or {})
        profile_quarantine_state = self._profile_quarantine_state(metadata)
        if self._profile_quarantine_blocks_primary_flow(metadata):
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.BLOCKED,
                DouyinAccountWarningLevel.BLOCK,
                "Profile quarantined",
                False,
                {
                    "reason": self._profile_quarantine_reason(metadata) or "profile_quarantined",
                    "profile_quarantine_state": profile_quarantine_state,
                    "profile_quarantine_recommended_next_action": self._profile_quarantine_recommended_next_action(metadata),
                },
                next_due,
                expires_at,
            )
        effective_challenge_state = self._effective_challenge_state(metadata, now=now)
        if effective_challenge_state in DOUYIN_CHALLENGE_UNRESOLVED_STATES or effective_challenge_state == "challenge_cooldown_active":
            if effective_challenge_state == "challenge_cooldown_active":
                label = "Challenge cooldown active"
                reason = "challenge_cooldown_active"
            elif effective_challenge_state == "challenge_repeat_limit_reached":
                label = "Challenge repeat limit reached"
                reason = "challenge_repeat_limit_reached"
            elif effective_challenge_state == "challenge_cooldown":
                label = "Challenge cooldown"
                reason = "challenge_cooldown"
            elif effective_challenge_state == "challenge_recently_solved_pending_recheck":
                label = "Challenge pending recheck"
                reason = "challenge_recently_solved_pending_recheck"
            else:
                label = "Manual challenge required"
                reason = effective_challenge_state or account.last_validation_status or "browser_validation_challenge_required"
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.BLOCKED,
                DouyinAccountWarningLevel.BLOCK,
                label,
                False,
                {
                    "reason": reason,
                    "challenge_state": effective_challenge_state,
                    "cooldown_until": metadata.get("douyin_challenge_cooldown_until"),
                },
                next_due,
                expires_at,
            )
        if account.status == DouyinAccountConnectionStatus.BLOCKED:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.BLOCKED,
                DouyinAccountWarningLevel.BLOCK,
                "Blocked",
                False,
                {"reason": account.last_validation_status or "blocked_response"},
                next_due,
                expires_at,
            )
        if account.status == DouyinAccountConnectionStatus.EXPIRED:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.EXPIRED,
                DouyinAccountWarningLevel.BLOCK,
                "Expired",
                False,
                {"reason": account.last_validation_status or "expired_session"},
                next_due,
                expires_at,
            )
        if account.status == DouyinAccountConnectionStatus.INVALID:
            if account.last_validated_at is None:
                return DouyinAccountHealthSummary(
                    DouyinAccountHealthStatus.UNKNOWN,
                    DouyinAccountWarningLevel.INFO,
                    "Needs validation",
                    False,
                    {"reason": "not_validated"},
                    next_due or now,
                    expires_at,
                )
            if account.last_validation_status == "browser_validation_inconclusive":
                return DouyinAccountHealthSummary(
                    DouyinAccountHealthStatus.UNKNOWN,
                    DouyinAccountWarningLevel.WARN,
                    "Browser validation inconclusive",
                    False,
                    {"reason": "browser_validation_inconclusive"},
                    next_due or now,
                    expires_at,
                )
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.INVALID,
                DouyinAccountWarningLevel.BLOCK,
                "Invalid",
                False,
                {"reason": account.last_validation_status or "invalid_session"},
                next_due or now,
                expires_at,
            )
        if account.status != DouyinAccountConnectionStatus.ACTIVE:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.UNKNOWN,
                DouyinAccountWarningLevel.INFO,
                "Unknown",
                False,
                {"reason": "unknown_status"},
                next_due or now,
                expires_at,
            )

        last_success = account.last_successful_validation_at or account.last_validated_at
        if last_success is None:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.UNKNOWN,
                DouyinAccountWarningLevel.INFO,
                "Needs validation",
                False,
                {"reason": "active_without_validation_timestamp"},
                next_due or now,
                expires_at,
            )
        if last_success.tzinfo is None:
            last_success = last_success.replace(tzinfo=UTC)
        age = now - last_success
        next_due = next_due or last_success + DOUYIN_ACCOUNT_FRESH_WINDOW
        if age > DOUYIN_ACCOUNT_EXPIRY_WARNING_WINDOW:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.EXPIRING_SOON,
                DouyinAccountWarningLevel.WARN,
                "Revalidate soon",
                True,
                {"reason": "heuristic_expiry_warning", "age_hours": int(age.total_seconds() // 3600)},
                next_due,
                expires_at,
            )
        if age > DOUYIN_ACCOUNT_FRESH_WINDOW:
            return DouyinAccountHealthSummary(
                DouyinAccountHealthStatus.STALE,
                DouyinAccountWarningLevel.WARN,
                "Stale",
                True,
                {"reason": "validation_stale", "age_hours": int(age.total_seconds() // 3600)},
                next_due,
                expires_at,
            )
        return DouyinAccountHealthSummary(
            DouyinAccountHealthStatus.HEALTHY,
            DouyinAccountWarningLevel.NONE,
            "Healthy",
            True,
            None,
            next_due,
            expires_at,
        )

    def due_for_revalidation(
        self,
        *,
        workspace_id: UUID | None = None,
        due_only: bool = True,
        now: datetime | None = None,
    ) -> list[DouyinAccountConnection]:
        now = now or datetime.now(UTC)
        stmt = select(DouyinAccountConnection).where(DouyinAccountConnection.status != DouyinAccountConnectionStatus.DISABLED)
        if workspace_id is not None:
            stmt = stmt.where(DouyinAccountConnection.workspace_id == workspace_id)
        if due_only:
            stmt = stmt.where(
                or_(
                    DouyinAccountConnection.next_validation_due_at.is_(None),
                    DouyinAccountConnection.next_validation_due_at <= now,
                    DouyinAccountConnection.health_status.in_(
                        [DouyinAccountHealthStatus.STALE, DouyinAccountHealthStatus.EXPIRING_SOON, DouyinAccountHealthStatus.UNKNOWN]
                    ),
                )
            )
        return list(self.db.scalars(stmt.order_by(DouyinAccountConnection.updated_at.asc())))

    def revalidate_due_accounts(
        self,
        *,
        workspace_id: UUID | None = None,
        due_only: bool = True,
        validation_source: str = "auto_revalidate",
    ) -> list[DouyinAccountConnection]:
        accounts = self.due_for_revalidation(workspace_id=workspace_id, due_only=due_only)
        validated: list[DouyinAccountConnection] = []
        for account in accounts:
            validated_account, _, _ = self.validate_account(account.id, validation_source=validation_source)
            validated.append(validated_account)
        return validated

    def resolve_runtime_config(self, account_id: UUID, *, require_active: bool = True) -> DouyinAccountRuntimeConfig:
        account = self.get_account(account_id)
        if require_active and account.status != DouyinAccountConnectionStatus.ACTIVE:
            raise DouyinAccountError(
                f"Douyin account connection is {account.status}; validate it before live fetch",
                code="account_resolution_failed",
            )
        health = self.health_summary(account)
        if require_active and not health.can_use_for_live_fetch:
            raise DouyinAccountError(
                f"Douyin account health is {health.health_status}; revalidate it before live fetch",
                code="account_resolution_failed",
            )
        self._refresh_session_from_live_browser_context(account)
        session_cookie = self._resolve_normalized_session_cookie(account)
        if not session_cookie:
            raise DouyinAccountError("Imported session is missing a valid Cookie header.", code="imported_session_missing_cookie")
        settings = get_settings()
        user_agent = account.user_agent or self._user_agent_from_headers(account.headers_json)
        if not user_agent and not self._is_manual_import_account(account):
            user_agent = settings.douyin_user_agent
        if not user_agent:
            raise DouyinAccountError("Imported account is missing a usable User-Agent.", code="imported_session_missing_user_agent")
        return DouyinAccountRuntimeConfig(
            account_id=account.id,
            session_cookie=session_cookie,
            user_agent=user_agent,
            proxy_url=account.proxy_url or settings.douyin_proxy_url,
        )

    def build_fetch_client(self, runtime: DouyinAccountRuntimeConfig) -> DouyinLiveFetchClient:
        settings = get_settings()
        return DouyinLiveFetchClient(
            DouyinLiveFetchConfig(
                user_agent=runtime.user_agent,
                session_cookie=runtime.session_cookie,
                proxy_url=runtime.proxy_url,
                timeout_seconds=settings.douyin_fetch_timeout_seconds,
                max_videos=settings.douyin_fetch_max_videos,
            ),
            http_get=self._http_get,
            browser_fetch=lambda profile_url: self._fetch_profile_via_browser_context(
                account_id=runtime.account_id,
                profile_url=profile_url,
                runtime=runtime,
            ),
            prefer_browser_profile=settings.douyin_prefer_browser_profile_for_fetch,
            allow_http_fallback=self._legacy_http_fallback_enabled(),
        )

    def build_douyin_adapter(self, account_id: UUID) -> DouyinProfileAdapter:
        runtime = self.resolve_runtime_config(account_id)
        return DouyinProfileAdapter(fetch_client=self.build_fetch_client(runtime))

    def preflight_fetch_readiness(self, account_id: UUID) -> DouyinFetchPreflightResult:
        account = self.get_account(account_id)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        browser_profile_id = metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None
        browser_profile_path = metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None
        browser_profile_exists = bool(browser_profile_id or browser_profile_path)
        quarantine_block = self._profile_quarantine_preflight_block(account, metadata, browser_profile_exists=browser_profile_exists)
        if quarantine_block is not None:
            self.invalidate_preflight_cache(account.id)
            return quarantine_block
        challenge_block = self._challenge_preflight_block(account, metadata, browser_profile_exists=browser_profile_exists)
        if challenge_block is not None:
            self.invalidate_preflight_cache(account.id)
            return challenge_block

        now = datetime.now(UTC)
        operator_confirmed_at = self._parse_metadata_datetime(metadata.get("operator_confirmed_ready_at"))
        if browser_profile_exists and self._operator_confirmation_valid(operator_confirmed_at, now=now):
            browser_context = douyin_browser_context_registry.summary_for_account(account.id)
            return self._store_preflight_result(
                account.id,
                DouyinFetchPreflightResult(
                    preflight_ran=True,
                    preflight_result="passed",
                    fetch_readiness_category="fetch_ready_operator_confirmed",
                    selected_fetch_path="browser_profile",
                    browser_profile_available=True,
                    browser_reopen_attempted=False,
                    browser_context_status=browser_context.status,
                    browser_context_reason="operator_confirmed_ready",
                    managed_runtime_status=getattr(browser_context, "managed_runtime_status", None),
                    profile_conflict_status=getattr(browser_context, "profile_conflict_status", None),
                    watchdog_result="operator_confirmed_ready",
                    watchdog_status=browser_context.status,
                    watchdog_reason="operator_confirmed_ready",
                ),
            )

        health = self.health_summary(account)
        if not health.can_use_for_live_fetch:
            self.invalidate_preflight_cache(account.id)
            return DouyinFetchPreflightResult(
                preflight_ran=True,
                preflight_result="failed",
                fetch_readiness_category="fetch_not_ready",
                selected_fetch_path=None,
                browser_profile_available=browser_profile_exists,
                browser_reopen_attempted=False,
                preflight_failure_code="account_not_fetch_ready",
                preflight_failure_message=f"Douyin account health is {health.health_status}; revalidate or choose another account before Intake fetch.",
                challenge_state=metadata.get("douyin_challenge_state") if isinstance(metadata.get("douyin_challenge_state"), str) else None,
                challenge_category=metadata.get("douyin_challenge_category") if isinstance(metadata.get("douyin_challenge_category"), str) else None,
                challenge_count=self._challenge_count(metadata),
                challenge_cooldown_until=self._parse_metadata_datetime(metadata.get("douyin_challenge_cooldown_until")),
                challenge_recommended_next_action=metadata.get("douyin_challenge_recommended_next_action") if isinstance(metadata.get("douyin_challenge_recommended_next_action"), str) else None,
            )

        cached = self._cached_preflight_result(account.id)
        if cached is not None:
            return cached

        settings = get_settings()

        if settings.douyin_prefer_browser_profile_for_fetch and browser_profile_exists:
            watchdog = douyin_browser_context_registry.watchdog_for_account(account.id)
            if watchdog.status == "active":
                return self._store_preflight_result(
                    account.id,
                    DouyinFetchPreflightResult(
                        preflight_ran=True,
                        preflight_result="passed",
                        fetch_readiness_category="fetch_ready_browser_profile",
                        selected_fetch_path="browser_profile",
                        browser_profile_available=True,
                        browser_reopen_attempted=False,
                        browser_reopen_result="already_active",
                        browser_context_status=watchdog.status,
                        browser_context_reason=watchdog.reason,
                        managed_runtime_status=getattr(watchdog, "managed_runtime_status", None),
                        profile_conflict_status=getattr(watchdog, "profile_conflict_status", None),
                        watchdog_result=watchdog.result,
                        watchdog_status=watchdog.status,
                        watchdog_reason=watchdog.reason,
                        runtime_reconciled=watchdog.runtime_reconciled,
                    ),
                )

            self._ensure_persistent_profile_context(account, purpose="fetch")
            self.db.commit()
            reopened_watchdog = douyin_browser_context_registry.watchdog_for_account(account.id)
            runtime_reconciled = watchdog.runtime_reconciled or reopened_watchdog.runtime_reconciled
            if reopened_watchdog.status == "active":
                return self._store_preflight_result(
                    account.id,
                    DouyinFetchPreflightResult(
                        preflight_ran=True,
                        preflight_result="passed",
                        fetch_readiness_category="fetch_ready_after_browser_reopen",
                        selected_fetch_path="browser_profile",
                        browser_profile_available=True,
                        browser_reopen_attempted=True,
                        browser_reopen_result="reopened",
                        browser_context_status=reopened_watchdog.status,
                        browser_context_reason=reopened_watchdog.reason,
                        managed_runtime_status=getattr(reopened_watchdog, "managed_runtime_status", None),
                        profile_conflict_status=getattr(reopened_watchdog, "profile_conflict_status", None),
                        watchdog_result=reopened_watchdog.result,
                        watchdog_status=reopened_watchdog.status,
                        watchdog_reason=reopened_watchdog.reason,
                        runtime_reconciled=runtime_reconciled,
                    ),
                )

            legacy_http_fallback_allowed = self._legacy_http_fallback_enabled()
            fallback_ready = legacy_http_fallback_allowed and self._has_http_fetch_material(account)
            if fallback_ready:
                return self._store_preflight_result(
                    account.id,
                    DouyinFetchPreflightResult(
                        preflight_ran=True,
                        preflight_result="passed",
                        fetch_readiness_category="fetch_ready_http_fallback",
                        selected_fetch_path="http_html",
                        browser_profile_available=False,
                        browser_reopen_attempted=True,
                        browser_reopen_result=reopened_watchdog.reason or reopened_watchdog.status,
                        browser_context_status=reopened_watchdog.status,
                        browser_context_reason=reopened_watchdog.reason,
                        managed_runtime_status=getattr(reopened_watchdog, "managed_runtime_status", None),
                        profile_conflict_status=getattr(reopened_watchdog, "profile_conflict_status", None),
                        watchdog_result=reopened_watchdog.result,
                        watchdog_status=reopened_watchdog.status,
                        watchdog_reason=reopened_watchdog.reason,
                        runtime_reconciled=runtime_reconciled,
                    ),
                )
            return DouyinFetchPreflightResult(
                preflight_ran=True,
                preflight_result="failed",
                fetch_readiness_category="fetch_not_ready",
                selected_fetch_path=None,
                browser_profile_available=False,
                browser_reopen_attempted=True,
                browser_reopen_result=reopened_watchdog.reason or reopened_watchdog.status,
                browser_context_status=reopened_watchdog.status,
                browser_context_reason=reopened_watchdog.reason,
                managed_runtime_status=getattr(reopened_watchdog, "managed_runtime_status", None),
                profile_conflict_status=getattr(reopened_watchdog, "profile_conflict_status", None),
                watchdog_result=reopened_watchdog.result,
                watchdog_status=reopened_watchdog.status,
                watchdog_reason=reopened_watchdog.reason,
                runtime_reconciled=runtime_reconciled,
                preflight_failure_code="profile_opened_outside_managed_runtime" if getattr(reopened_watchdog, "profile_conflict_status", None) == "profile_opened_outside_managed_runtime" else "browser_profile_unavailable",
                preflight_failure_message=(
                    "The saved Douyin browser profile is open outside the app-managed runtime. Close the external browser window/process for this profile, then use Open profile from this app before Intake."
                    if getattr(reopened_watchdog, "profile_conflict_status", None) == "profile_opened_outside_managed_runtime"
                    else "Reusable browser profile could not be reopened. Connected-account Intake now requires the saved browser profile; legacy HTTP fallback is disabled by default."
                ),
            )

        if self._legacy_http_fallback_enabled() and self._has_http_fetch_material(account):
            return self._store_preflight_result(
                account.id,
                DouyinFetchPreflightResult(
                    preflight_ran=True,
                    preflight_result="passed",
                    fetch_readiness_category="fetch_ready_http_fallback",
                    selected_fetch_path="http_html",
                    browser_profile_available=False,
                    browser_reopen_attempted=False,
                    browser_context_status="none",
                    browser_context_reason="no_reusable_browser_profile",
                    watchdog_result="missing",
                    watchdog_status="none",
                    watchdog_reason="no_reusable_browser_profile",
                ),
            )
        self.invalidate_preflight_cache(account.id)
        return DouyinFetchPreflightResult(
            preflight_ran=True,
            preflight_result="failed",
            fetch_readiness_category="fetch_not_ready",
            selected_fetch_path=None,
            browser_profile_available=False,
            browser_reopen_attempted=False,
            preflight_failure_code="browser_profile_required",
            preflight_failure_message="Selected Douyin account does not have a reusable browser profile. Create or reopen a browser-profile-backed account before running Intake.",
            watchdog_result="missing",
            watchdog_status="none",
            watchdog_reason="no_reusable_browser_profile",
        )

    def _fetch_profile_via_browser_context(
        self,
        *,
        account_id: UUID,
        profile_url: str,
        runtime: DouyinAccountRuntimeConfig,
    ) -> dict:
        settings = get_settings()
        account = self.get_account(account_id)
        self._ensure_persistent_profile_context(account, purpose="fetch")
        result = douyin_browser_context_registry.fetch_profile_page(account_id, profile_url=profile_url)
        metadata = {
            "source": "douyin_browser_profile",
            "response_shape": "browser_rendered_html",
            "browser_context_status": result.status,
            "browser_context_reason": result.reason,
            "browser_managed_runtime_status": result.managed_runtime_status,
            "browser_profile_conflict_status": result.profile_conflict_status,
            "browser_runtime_attach_status": result.runtime_attach_status,
            "browser_page_recovery_status": result.page_recovery_status,
            "browser_runtime_context_id": result.runtime_context_id,
            "browser_profile_id": (getattr(account, "metadata_json", None) or {}).get("browser_profile_id"),
            "browser_page_url": result.page_url,
            "browser_page_title": result.title,
            "browser_video_link_count": result.video_link_count,
            "browser_response_document_count": result.response_document_count,
            "profile_payload_present": False,
            "video_candidate_count": 0,
            "browser_fetch_user_agent": result.user_agent or runtime.user_agent,
        }
        if result.user_agent and result.user_agent != account.user_agent:
            account.user_agent = result.user_agent
            self.db.commit()
        if not result.available or not result.html:
            payload = {
                "profile": {},
                "videos": [],
                "metadata": {
                    **metadata,
                    "response_classification": {
                        "result": "failed",
                        "code": "browser_profile_unavailable",
                        "message": "Reusable browser profile was not available for Douyin fetch.",
                        "blocked_reason": result.reason,
                        "metrics": {
                            "video_link_count": result.video_link_count,
                        },
                    },
                },
            }
            raise SourceAdapterError(
                SourceAdapterErrorCode.ADAPTER_FETCH_FAILED,
                "Reusable browser profile was not available for Douyin fetch.",
                raw_payload=payload,
            )
        payload = extract_profile_payload_from_browser_artifacts(
            html=result.html,
            profile_url=profile_url,
            response_documents=result.response_documents,
            video_links=result.video_links,
            page_title=result.title,
            page_url=result.page_url,
            max_videos=settings.douyin_fetch_max_videos,
        )
        payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        payload["metadata"] = {**metadata, **payload_metadata}
        return payload

    def _has_http_fetch_material(self, account: DouyinAccountConnection) -> bool:
        try:
            cookie = self._resolve_normalized_session_cookie(account)
        except DouyinAccountError:
            return False
        if not cookie:
            return False
        user_agent = account.user_agent or self._user_agent_from_headers(account.headers_json) or get_settings().douyin_user_agent
        return bool(user_agent)

    def to_response(self, account: DouyinAccountConnection) -> DouyinAccountResponse:
        session_cookie = self._decode_session_cookie(account.session_secret_blob)
        health = self.health_summary(account)
        browser_context = douyin_browser_context_registry.summary_for_account(account.id)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        browser_context_status = browser_context.status
        has_saved_profile = isinstance(metadata.get("browser_profile_id"), str) or isinstance(metadata.get("browser_profile_path"), str)
        if browser_context_status == "none" and has_saved_profile:
            browser_context_status = "profile_saved"
        browser_context_id = browser_context.runtime_context_id
        if browser_context_id is None and has_saved_profile:
            browser_context_id, _ = douyin_browser_context_registry.profile_identity_for_account(
                account.id,
                browser_profile_id=metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None,
                browser_profile_path=metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None,
            )
        manual_import_preflight = self._manual_import_preflight_summary(account) if self._legacy_debug_surfaces_enabled() else None
        browser_health_alignment = self._browser_health_alignment_summary(
            account,
            browser_context_status=browser_context_status,
            browser_context_available=browser_context.status == "active",
            has_saved_profile=has_saved_profile,
        )
        return DouyinAccountResponse(
            id=account.id,
            workspace_id=account.workspace_id,
            display_name=account.display_name,
            douyin_user_id=account.douyin_user_id,
            status=account.status,
            is_default=account.is_default,
            session_cookie_present=bool(session_cookie),
            session_cookie_preview=self._preview_secret(session_cookie),
            user_agent=account.user_agent,
            proxy_url=account.proxy_url,
            headers_json=account.headers_json,
            health_status=health.health_status,
            warning_level=health.warning_level,
            last_validated_at=account.last_validated_at,
            last_successful_validation_at=account.last_successful_validation_at,
            last_validation_status=account.last_validation_status,
            validation_source=account.validation_source,
            next_validation_due_at=health.next_validation_due_at,
            expires_at=health.expires_at,
            last_error_code=account.last_error_code,
            last_error_message=account.last_error_message,
            account_health_label=health.label,
            can_use_for_live_fetch=health.can_use_for_live_fetch,
            warning_summary_json=health.warning_summary,
            browser_context_available=browser_context.status == "active",
            browser_context_status=browser_context_status,
            browser_context_id=browser_context_id,
            browser_context_last_used_at=browser_context.last_used_at,
            manual_import_preflight=manual_import_preflight,
            browser_health_alignment=browser_health_alignment,
            metadata_json=account.metadata_json,
            notes=account.notes,
            created_at=account.created_at,
            updated_at=account.updated_at,
        )

    def _browser_health_alignment_summary(
        self,
        account: DouyinAccountConnection,
        *,
        browser_context_status: str | None,
        browser_context_available: bool,
        has_saved_profile: bool,
    ) -> DouyinBrowserHealthAlignmentSummary:
        metadata = dict(getattr(account, "metadata_json", None) or {})
        live_runtime_summary = douyin_browser_context_registry.summary_for_account(account.id)
        live_runtime_status = getattr(live_runtime_summary, "status", None)
        live_managed_runtime_status = getattr(live_runtime_summary, "managed_runtime_status", None)
        live_page_recovery_reason = getattr(live_runtime_summary, "reason", None)
        live_page_recovery_status = live_page_recovery_reason if live_runtime_status == "active" else None
        live_profile_conflict_status = getattr(live_runtime_summary, "profile_conflict_status", None)
        validation_source = account.validation_source or "unknown"
        last_validation_status = account.last_validation_status
        last_error_code = account.last_error_code
        last_error_message = account.last_error_message
        last_browser_validation_status = metadata.get("last_browser_context_status")
        if not isinstance(last_browser_validation_status, str):
            last_browser_validation_status = None
        last_browser_validation_reason = metadata.get("last_browser_context_reason")
        if not isinstance(last_browser_validation_reason, str):
            last_browser_validation_reason = None
        last_browser_validation_at_raw = metadata.get("browser_context_checked_at")
        last_browser_validation_at: datetime | None = None
        if isinstance(last_browser_validation_at_raw, str) and last_browser_validation_at_raw:
            try:
                last_browser_validation_at = datetime.fromisoformat(last_browser_validation_at_raw)
            except ValueError:
                last_browser_validation_at = None

        if browser_context_available:
            interactive_browser_state = "live"
        elif has_saved_profile:
            interactive_browser_state = "saved"
        else:
            interactive_browser_state = "missing"

        final_validation_category = metadata.get("last_browser_validation_final_category")
        if not isinstance(final_validation_category, str):
            final_validation_category = metadata.get("last_browser_validation_category")
        if not isinstance(final_validation_category, str):
            final_validation_category = None
        persisted_challenge_state = metadata.get("douyin_challenge_state")
        if not isinstance(persisted_challenge_state, str):
            persisted_challenge_state = None
        profile_quarantine_state = self._profile_quarantine_state(metadata)
        profile_quarantine_reason = self._profile_quarantine_reason(metadata)
        profile_quarantine_detected = self._profile_quarantine_detected(metadata)
        profile_quarantine_recommended_next_action = self._profile_quarantine_recommended_next_action(metadata)
        profile_quarantine_blocks_primary_flow = self._profile_quarantine_blocks_primary_flow(metadata)
        profile_quarantine_replaced_by_account_id = self._profile_quarantine_replaced_by_account_id(metadata)
        challenge_state = self._effective_challenge_state(metadata, now=datetime.now(UTC))
        challenge_category = metadata.get("douyin_challenge_category")
        if not isinstance(challenge_category, str):
            challenge_category = metadata.get("last_browser_validation_challenge_category")
        if not isinstance(challenge_category, str):
            challenge_category = None
        recommended_next_action = metadata.get("douyin_challenge_recommended_next_action")
        if not isinstance(recommended_next_action, str):
            recommended_next_action = metadata.get("last_browser_validation_recommended_next_action")
        if not isinstance(recommended_next_action, str):
            recommended_next_action = None
        challenge_last_detected_at = self._parse_metadata_datetime(metadata.get("douyin_challenge_last_detected_at"))
        challenge_last_solved_at = self._parse_metadata_datetime(metadata.get("douyin_challenge_last_solved_at"))
        challenge_cooldown_until = self._parse_metadata_datetime(metadata.get("douyin_challenge_cooldown_until"))

        automated_browser_validation_state = "not_available"
        if challenge_state in DOUYIN_CHALLENGE_UNRESOLVED_STATES or challenge_state == "challenge_cooldown_active":
            if challenge_state == "challenge_recently_solved_pending_recheck":
                automated_browser_validation_state = "manual_verification_pending_recheck"
            elif challenge_state == "challenge_cooldown_active":
                automated_browser_validation_state = "challenge_cooldown_active"
            elif challenge_state == "challenge_cooldown":
                automated_browser_validation_state = "challenge_cooldown"
            elif challenge_state == "challenge_repeat_limit_reached":
                automated_browser_validation_state = "challenge_repeat_limit_reached"
            elif challenge_category == "captcha_required":
                automated_browser_validation_state = "captcha_required"
            elif challenge_category == "challenge_required":
                automated_browser_validation_state = "challenge_required"
            else:
                automated_browser_validation_state = "manual_verification_required"
        elif has_saved_profile or last_browser_validation_status is not None:
            automated_browser_validation_state = "unknown"
            if account.status == DouyinAccountConnectionStatus.ACTIVE and last_validation_status in {
                "browser_context_session_reachable",
                "browser_validation_success",
            }:
                automated_browser_validation_state = "passed"
            elif last_validation_status == "browser_validation_captcha_required":
                automated_browser_validation_state = "captcha_required"
            elif last_validation_status == "browser_validation_challenge_required":
                automated_browser_validation_state = "challenge_required"
            elif last_validation_status == "browser_validation_manual_verification_required":
                automated_browser_validation_state = "manual_verification_required"
            elif last_validation_status in {"browser_context_blocked_retryable", "browser_validation_inconclusive"}:
                automated_browser_validation_state = "inconclusive"
            elif account.status == DouyinAccountConnectionStatus.BLOCKED and (
                validation_source.startswith("browser") or last_browser_validation_status == "blocked"
            ):
                automated_browser_validation_state = "blocked"
            elif last_validation_status == "browser_validation_blocked":
                automated_browser_validation_state = "blocked"
            elif account.status == DouyinAccountConnectionStatus.EXPIRED and last_browser_validation_status == "login_required":
                automated_browser_validation_state = "login_required"
            elif last_validation_status == "browser_validation_login_required":
                automated_browser_validation_state = "login_required"
            elif last_browser_validation_status == "passed":
                automated_browser_validation_state = "passed"
            elif last_browser_validation_status == "blocked":
                if final_validation_category == "browser_validation_captcha_required":
                    automated_browser_validation_state = "captcha_required"
                elif final_validation_category == "browser_validation_challenge_required":
                    automated_browser_validation_state = "challenge_required"
                elif final_validation_category == "browser_validation_manual_verification_required":
                    automated_browser_validation_state = "manual_verification_required"
                else:
                    automated_browser_validation_state = "blocked"
            elif last_browser_validation_status == "login_required":
                automated_browser_validation_state = "login_required"
            elif metadata.get("last_browser_validation_profile_conflict_status") == "profile_opened_outside_managed_runtime":
                automated_browser_validation_state = "profile_opened_outside_managed_runtime"
            elif last_validation_status == "profile_reopen_failed":
                automated_browser_validation_state = "profile_reopen_failed"
            elif last_validation_status == "runtime_attach_failed":
                automated_browser_validation_state = "runtime_attach_failed"
            elif last_validation_status == "browser_validation_runtime_unavailable" and last_error_message == "no_live_browser_context":
                automated_browser_validation_state = "runtime_missing"
            elif metadata.get("last_browser_validation_reopen_status") == "browser_validation_runtime_reopened":
                automated_browser_validation_state = "runtime_reopened"
            elif last_browser_validation_status == "uncertain":
                automated_browser_validation_state = "inconclusive"

        legacy_http_fallback_enabled = self._legacy_http_fallback_enabled()
        detached_http_state = "disabled" if not legacy_http_fallback_enabled else "not_applicable"
        if legacy_http_fallback_enabled and self._has_http_fetch_material(account):
            detached_http_state = "available"
            if validation_source.startswith("http"):
                detached_http_state = "failed" if account.status in {
                    DouyinAccountConnectionStatus.BLOCKED,
                    DouyinAccountConnectionStatus.EXPIRED,
                    DouyinAccountConnectionStatus.INVALID,
                } else "passed"
            elif last_error_code == "blocked_response" and not validation_source.startswith("browser"):
                detached_http_state = "failed"

        effective_validation_path = "unknown"
        if validation_source.startswith("browser") or last_browser_validation_status is not None:
            effective_validation_path = "browser_profile"
        elif validation_source.startswith("http") and legacy_http_fallback_enabled:
            effective_validation_path = "detached_http"
        elif has_saved_profile or not legacy_http_fallback_enabled:
            effective_validation_path = "browser_profile"

        expected_intake_path = "detached_http" if legacy_http_fallback_enabled and not has_saved_profile else "browser_profile"
        validation_intake_aligned = effective_validation_path == expected_intake_path
        stale_blocked_state_cleared = (
            has_saved_profile
            and account.status == DouyinAccountConnectionStatus.ACTIVE
            and last_validation_status in {"browser_context_session_reachable", "browser_validation_success"}
            and last_browser_validation_status == "passed"
        )

        if profile_quarantine_blocks_primary_flow:
            browser_evidence_strength = "strong_negative"
        elif stale_blocked_state_cleared or automated_browser_validation_state == "passed":
            browser_evidence_strength = "strong"
        elif challenge_state in DOUYIN_CHALLENGE_UNRESOLVED_STATES or challenge_state == "challenge_cooldown_active":
            browser_evidence_strength = "strong_negative"
        elif automated_browser_validation_state in {"blocked", "login_required", "captcha_required", "challenge_required", "manual_verification_required"}:
            browser_evidence_strength = "strong_negative"
        elif automated_browser_validation_state in {"profile_reopen_failed", "runtime_attach_failed", "profile_opened_outside_managed_runtime"}:
            browser_evidence_strength = "recoverable_runtime_failure"
        elif automated_browser_validation_state in {"inconclusive", "retryable_blocked", "runtime_reopened", "runtime_missing"}:
            browser_evidence_strength = "partial"
        elif interactive_browser_state in {"live", "saved"}:
            browser_evidence_strength = "partial"
        else:
            browser_evidence_strength = "none"

        if profile_quarantine_blocks_primary_flow:
            operator_summary = "This saved Douyin browser profile is quarantined from the primary Intake flow."
            operator_detail = DOUYIN_PROFILE_QUARANTINE_RECOMMENDATION
        elif challenge_state == "challenge_recently_solved_pending_recheck":
            operator_summary = "Douyin challenge was marked solved and is waiting for browser-backed recheck."
            operator_detail = "Run the post-challenge validation retry in the same saved browser profile before using this account for Intake."
        elif challenge_state == "challenge_cooldown_active":
            operator_summary = "Douyin challenge cooldown is active for this saved browser profile."
            operator_detail = "The managed runtime can be healthy while Douyin challenge cooldown still blocks Intake. Complete the challenge in the saved profile, then use Mark challenge solved for browser-backed recovery."
        elif challenge_state == "challenge_cooldown":
            operator_summary = "Douyin challenge is in cooldown after repeated challenge detection."
            operator_detail = "Wait for the cooldown, complete the visible challenge in the saved browser profile, then mark it solved and recheck."
        elif challenge_state == "challenge_repeat_limit_reached":
            operator_summary = "Douyin challenge repeated too many times for automatic Intake resume."
            operator_detail = "Use the saved browser profile to complete verification, wait out cooldown if present, then mark solved and run post-challenge validation."
        elif challenge_state == "challenge_waiting_for_manual_verification":
            operator_summary = "Douyin browser challenge is waiting for manual verification."
            operator_detail = "Complete the visible captcha/security verification in the saved browser profile, then mark the challenge solved."
        elif stale_blocked_state_cleared:
            operator_summary = "Browser-backed validation passed and the account is active again."
            operator_detail = "The reusable browser profile produced stronger evidence than older blocked state, so Intake and validation are aligned on the browser-profile path."
        elif automated_browser_validation_state == "passed":
            operator_summary = "Browser-backed validation passed for this reusable profile."
            operator_detail = "Validation and Intake are using the same browser-profile-backed path."
        elif automated_browser_validation_state == "runtime_reopened":
            operator_summary = "Validate auto-reopened the saved browser profile."
            operator_detail = "The missing live browser runtime was recovered from the saved reusable profile, then validation continued on the browser-profile path."
        elif automated_browser_validation_state == "profile_opened_outside_managed_runtime":
            operator_summary = "The saved browser profile is open outside the app-managed runtime."
            operator_detail = "Close the external Douyin browser window/process for this profile, then use Open profile from this app so Validate, Mark challenge solved, and Intake share the managed runtime."
        elif automated_browser_validation_state == "profile_reopen_failed":
            operator_summary = "Validate tried to reopen the saved browser profile, but reopening failed."
            operator_detail = last_browser_validation_reason or last_error_message
        elif automated_browser_validation_state == "runtime_attach_failed":
            operator_summary = "Validate reopened a runtime, but it was not safely attached to this account/profile."
            operator_detail = last_browser_validation_reason or last_error_message
        elif automated_browser_validation_state == "runtime_missing":
            operator_summary = "Saved browser profile exists, but the live runtime is missing."
            operator_detail = "Validate will try to auto-reopen the saved profile before reporting runtime unavailable."
        elif automated_browser_validation_state == "captcha_required":
            operator_summary = "Browser-backed validation reached a captcha challenge."
            operator_detail = "Solve the captcha in the open reusable browser profile, then retry validation."
        elif automated_browser_validation_state == "challenge_required":
            operator_summary = "Browser-backed validation reached a Douyin security challenge."
            operator_detail = "Complete the challenge in the open reusable browser profile, then retry validation."
        elif automated_browser_validation_state == "manual_verification_required":
            operator_summary = "Browser-backed validation requires manual verification in the browser profile."
            operator_detail = "Review the open reusable browser profile, complete any visible verification, then retry validation."
        elif automated_browser_validation_state in {"inconclusive", "retryable_blocked"}:
            operator_summary = "Browser-backed validation is inconclusive and retryable."
            operator_detail = "Validate reached the reusable browser profile, but the browser probe did not produce final success or hard-block evidence. Detached HTTP fallback is not treated as stronger evidence for this browser-backed account."
        elif automated_browser_validation_state == "blocked":
            operator_summary = "Browser-backed validation reported this profile as blocked."
            operator_detail = last_browser_validation_reason or last_error_message
        elif automated_browser_validation_state == "login_required":
            operator_summary = "Browser-backed validation requires login again."
            operator_detail = last_browser_validation_reason or last_error_message
        elif interactive_browser_state == "live":
            operator_summary = "A reusable browser profile is live, but no conclusive browser-backed validation is recorded yet."
            operator_detail = "Run validation again to overwrite older persisted status with current browser evidence."
        elif interactive_browser_state == "saved":
            operator_summary = "A reusable browser profile is saved for this account."
            operator_detail = "Run browser-backed validation; Validate can auto-reopen the saved profile so Intake and validation use the same path."
        elif detached_http_state == "available":
            operator_summary = "This account currently depends on detached HTTP session material."
            operator_detail = "Detached HTTP fallback is weaker evidence than a reusable browser profile for connected accounts."
        else:
            operator_summary = "No reusable browser profile evidence is available for this account."
            operator_detail = None

        auto_reopen_attempted = bool(metadata.get("last_browser_validation_auto_reopen_attempted"))
        auto_reopen_status = metadata.get("last_browser_validation_reopen_status") if auto_reopen_attempted else None
        if not isinstance(auto_reopen_status, str):
            auto_reopen_status = None
        runtime_reattached = bool(metadata.get("last_browser_validation_runtime_reattached")) if auto_reopen_attempted else False
        validation_continued_after_reopen = bool(metadata.get("last_browser_validation_continued_after_reopen")) if auto_reopen_attempted else False

        return DouyinBrowserHealthAlignmentSummary(
            interactive_browser_state=interactive_browser_state,
            automated_browser_validation_state=automated_browser_validation_state,
            detached_http_state=detached_http_state,
            effective_validation_path=effective_validation_path,
            expected_intake_path=expected_intake_path,
            validation_intake_aligned=validation_intake_aligned,
            stale_blocked_state_cleared=stale_blocked_state_cleared,
            browser_evidence_strength=browser_evidence_strength,
            operator_summary=operator_summary,
            operator_detail=operator_detail,
            last_browser_validation_status=last_browser_validation_status,
            last_browser_validation_reason=last_browser_validation_reason,
            last_browser_validation_at=last_browser_validation_at,
            runtime_attach_status=(
                "managed_runtime_active"
                if browser_context_available
                else metadata.get("last_browser_validation_runtime_attach_status")
                if isinstance(metadata.get("last_browser_validation_runtime_attach_status"), str)
                else None
            ),
            page_recovery_status=(
                live_page_recovery_status
                or (
                    metadata.get("last_browser_validation_page_recovery_status")
                    if isinstance(metadata.get("last_browser_validation_page_recovery_status"), str)
                    else None
                )
            ),
            managed_runtime_status=(
                live_managed_runtime_status
                or (
                    metadata.get("last_browser_validation_managed_runtime_status")
                    if isinstance(metadata.get("last_browser_validation_managed_runtime_status"), str)
                    else None
                )
            ),
            profile_conflict_status=(
                live_profile_conflict_status
                or (
                    metadata.get("last_browser_validation_profile_conflict_status")
                    if isinstance(metadata.get("last_browser_validation_profile_conflict_status"), str)
                    else None
                )
            ),
            auto_reopen_attempted=auto_reopen_attempted,
            auto_reopen_succeeded=auto_reopen_status in {"browser_validation_runtime_reopened", "reopen_success"},
            auto_reopen_status=auto_reopen_status,
            runtime_reattached=runtime_reattached,
            validation_continued_after_reopen=validation_continued_after_reopen,
            final_validation_category=final_validation_category,
            validation_attempt_id=metadata.get("last_browser_validation_attempt_id") if isinstance(metadata.get("last_browser_validation_attempt_id"), str) else None,
            challenge_category=challenge_category,
            recommended_next_action=recommended_next_action,
            challenge_state=challenge_state,
            challenge_detected=bool(metadata.get("douyin_challenge_detected")) or challenge_state is not None,
            challenge_count=self._challenge_count(metadata),
            profile_quarantine_state=profile_quarantine_state,
            profile_quarantine_reason=profile_quarantine_reason,
            profile_quarantine_detected=profile_quarantine_detected,
            profile_quarantine_recommended_next_action=profile_quarantine_recommended_next_action,
            profile_quarantine_blocks_primary_flow=profile_quarantine_blocks_primary_flow,
            profile_quarantine_replaced_by_account_id=profile_quarantine_replaced_by_account_id,
            profile_quarantine_clean_profile_recommendation=(
                DOUYIN_PROFILE_QUARANTINE_RECOMMENDATION if profile_quarantine_detected else None
            ),
            challenge_last_detected_at=challenge_last_detected_at,
            challenge_last_solved_at=challenge_last_solved_at,
            challenge_cooldown_until=challenge_cooldown_until,
            challenge_repeat_limit_reached=persisted_challenge_state == "challenge_repeat_limit_reached",
            challenge_recheck_attempt_id=metadata.get("douyin_challenge_recheck_attempt_id") if isinstance(metadata.get("douyin_challenge_recheck_attempt_id"), str) else None,
            challenge_recheck_started_at=self._parse_metadata_datetime(metadata.get("douyin_challenge_recheck_started_at")),
            challenge_recheck_resolved=bool(metadata.get("douyin_challenge_recheck_resolved")),
            challenge_same_runtime_reused=bool(metadata.get("douyin_challenge_same_runtime_reused")),
            mark_challenge_solved_attempted=bool(metadata.get("douyin_challenge_mark_solved_attempted")),
            post_challenge_recheck_result=metadata.get("douyin_challenge_postcheck_result") if isinstance(metadata.get("douyin_challenge_postcheck_result"), str) else None,
            same_profile_reused=bool(metadata.get("douyin_challenge_same_profile_reused")),
            runtime_reopened_for_recheck=bool(metadata.get("douyin_challenge_runtime_reopened_for_recheck")),
            intake_ready_after_recheck=bool(metadata.get("douyin_challenge_intake_ready_after_recheck")),
        )

    def _clear_default(self, workspace_id: UUID) -> None:
        for account in self.db.scalars(
            select(DouyinAccountConnection).where(
                DouyinAccountConnection.workspace_id == workspace_id,
                DouyinAccountConnection.is_default.is_(True),
            )
        ):
            account.is_default = False

    def _is_soft_deleted(self, account: DouyinAccountConnection) -> bool:
        metadata = account.metadata_json or {}
        return metadata.get("delete_mode") == DOUYIN_ACCOUNT_DELETE_MODE

    def _has_active_browser_connect_session(self, account_id: UUID) -> bool:
        stmt = select(DouyinBrowserConnectSession).where(
            DouyinBrowserConnectSession.derived_account_id == account_id,
            DouyinBrowserConnectSession.status.in_(tuple(RUNNING_BROWSER_CONNECT_STATUSES)),
        )
        return self.db.scalar(stmt.limit(1)) is not None

    def _deleted_display_name(self, display_name: str, account_id: UUID, deleted_at: datetime) -> str:
        suffix = f" [deleted {deleted_at:%Y%m%d%H%M%S} {str(account_id)[:8]}]"
        return f"{display_name[: 180 - len(suffix)]}{suffix}"

    def _validate_with_live_browser_context(
        self,
        *,
        account: DouyinAccountConnection,
        validation_url: str | None,
        now: datetime,
        validation_source: str,
    ) -> tuple[bool, str] | None:
        settings = get_settings()
        if not settings.douyin_reuse_live_browser_for_validation:
            return None
        target_validation_url = self._safe_validation_url(validation_url)
        metadata = self._start_browser_validation_attempt_metadata(account, now=now)
        saved_profile_id = metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None
        saved_profile_path = metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None
        has_saved_profile = bool(saved_profile_id or saved_profile_path)
        resolved_profile_id: str | None = None
        resolved_profile_path: str | None = None
        if has_saved_profile:
            resolved_profile_id, resolved_profile_path = douyin_browser_context_registry.profile_identity_for_account(
                account.id,
                browser_profile_id=saved_profile_id,
                browser_profile_path=saved_profile_path,
            )
            metadata["last_browser_validation_has_saved_profile"] = True
            metadata["last_browser_validation_saved_profile_id"] = resolved_profile_id
            account.metadata_json = metadata

        result = douyin_browser_context_registry.validate_account_context(account.id, validation_url=target_validation_url)
        metadata = dict(getattr(account, "metadata_json", None) or {})
        validation_continued_after_reopen = False
        metadata["last_browser_validation_runtime_attach_status"] = getattr(result, "runtime_attach_status", None)
        metadata["last_browser_validation_page_recovery_status"] = getattr(result, "page_recovery_status", None)
        metadata["last_browser_validation_managed_runtime_status"] = getattr(result, "managed_runtime_status", None)
        metadata["last_browser_validation_profile_conflict_status"] = getattr(result, "profile_conflict_status", None)
        metadata["last_browser_validation_attach_first_attempted"] = True
        account.metadata_json = metadata
        if has_saved_profile and result.status in {"none", "stale", "invalid", "closed"} and getattr(result, "runtime_attach_status", None) == "runtime_missing_reopen_required":
            metadata["last_browser_validation_auto_reopen_attempted"] = True
            metadata["last_browser_validation_auto_reopen_started_at"] = now.isoformat()
            metadata["last_browser_validation_reopen_status"] = "runtime_missing_reopen_required"
            metadata["last_browser_validation_reopen_reason"] = result.reason or "no_live_browser_context"
            metadata["last_browser_validation_runtime_reattached"] = False
            metadata["last_browser_validation_continued_after_reopen"] = False
            account.metadata_json = metadata

            reopen_summary = self._ensure_persistent_profile_context(account, purpose="validation", force=True)
            metadata = dict(getattr(account, "metadata_json", None) or {})
            if reopen_summary is None or reopen_summary.status != "active" or not reopen_summary.runtime_context_id:
                reason = (reopen_summary.reason if reopen_summary is not None else None) or "persistent_profile_reopen_failed"
                if reopen_summary is not None:
                    metadata["last_browser_validation_managed_runtime_status"] = getattr(reopen_summary, "managed_runtime_status", None)
                    metadata["last_browser_validation_profile_conflict_status"] = getattr(reopen_summary, "profile_conflict_status", None)
                return self._set_browser_validation_failure(
                    account,
                    metadata=metadata,
                    now=now,
                    category="profile_reopen_failed",
                    error_code="browser_validation_runtime_unavailable",
                    reason=reason,
                    context_status=reopen_summary.status if reopen_summary is not None else "none",
                    runtime_context_id=reopen_summary.runtime_context_id if reopen_summary is not None else None,
                    auto_reopen_status="failed",
                    runtime_reattached=False,
                    validation_continued=False,
                )

            attach_failure_reason = self._browser_reopen_attach_failure_reason(
                account=account,
                reopen_summary=reopen_summary,
                expected_profile_id=resolved_profile_id,
                expected_profile_path=resolved_profile_path,
            )
            if attach_failure_reason is not None:
                return self._set_browser_validation_failure(
                    account,
                    metadata=metadata,
                    now=now,
                    category="runtime_attach_failed",
                    error_code="browser_validation_runtime_unavailable",
                    reason=attach_failure_reason,
                    context_status=reopen_summary.status,
                    runtime_context_id=reopen_summary.runtime_context_id,
                    auto_reopen_status="reattach_failed",
                    runtime_reattached=False,
                    validation_continued=False,
                )

            metadata["last_browser_validation_reopen_status"] = "reopen_success"
            metadata["last_browser_validation_reopen_reason"] = reopen_summary.reason or "persistent_profile_reopened"
            metadata["last_browser_validation_reopen_at"] = now.isoformat()
            metadata["last_browser_validation_runtime_reattached"] = True
            metadata["last_browser_validation_runtime_reattached_at"] = now.isoformat()
            metadata["last_browser_validation_reattached_context_id"] = reopen_summary.runtime_context_id
            metadata["last_browser_validation_continued_after_reopen"] = True
            account.metadata_json = metadata
            result = douyin_browser_context_registry.validate_account_context(account.id, validation_url=target_validation_url)
            metadata["last_browser_validation_runtime_attach_status"] = getattr(result, "runtime_attach_status", None)
            metadata["last_browser_validation_page_recovery_status"] = getattr(result, "page_recovery_status", None)
            metadata["last_browser_validation_managed_runtime_status"] = getattr(result, "managed_runtime_status", None)
            metadata["last_browser_validation_profile_conflict_status"] = getattr(result, "profile_conflict_status", None)
            account.metadata_json = metadata
            validation_continued_after_reopen = True
        if result.cookie_header:
            account.session_secret_blob = self._encode_session_cookie(result.cookie_header)
        if result.user_agent:
            account.user_agent = result.user_agent
        metadata = dict(getattr(account, "metadata_json", None) or {})
        metadata["last_browser_context_status"] = result.status
        metadata["last_browser_context_reason"] = result.reason
        metadata["browser_context_id"] = result.runtime_context_id
        metadata["browser_context_checked_at"] = now.isoformat()
        metadata["last_browser_validation_runtime_attach_status"] = getattr(result, "runtime_attach_status", None)
        metadata["last_browser_validation_page_recovery_status"] = getattr(result, "page_recovery_status", None)
        metadata["last_browser_validation_managed_runtime_status"] = getattr(result, "managed_runtime_status", None)
        metadata["last_browser_validation_profile_conflict_status"] = getattr(result, "profile_conflict_status", None)
        metadata["last_browser_validation_continued_after_reopen"] = validation_continued_after_reopen
        if validation_continued_after_reopen:
            metadata["last_browser_validation_final_category"] = result.status
        account.metadata_json = metadata
        has_saved_profile = bool(metadata.get("browser_profile_id") or metadata.get("browser_profile_path"))
        if result.status == "passed" and result.cookie_header:
            metadata["browser_context_blocked_count"] = 0
            if self._profile_quarantine_state(metadata) == "quarantine_candidate":
                metadata["douyin_profile_quarantine_state"] = "quarantined_recoverable"
            metadata["last_browser_validation_category"] = "browser_validation_success"
            metadata["last_browser_validation_final_category"] = "browser_validation_success"
            self._clear_challenge_metadata(metadata)
            account.metadata_json = metadata
            account.status = DouyinAccountConnectionStatus.ACTIVE
            account.last_validation_status = "browser_validation_success"
            account.last_error_code = None
            account.last_error_message = None
            account.last_successful_validation_at = now
            self._apply_health_projection(account, now=now)
            return True, "browser_validation_success"
        if result.status == "blocked":
            blocked_count = int(metadata.get("browser_context_blocked_count", 0)) + 1
            category, challenge_category, recommended_next_action = self._classify_browser_validation_challenge(result.reason)
            challenge_state, recommended_next_action = self._set_challenge_detected_metadata(
                metadata,
                now=now,
                category=category,
                challenge_category=challenge_category,
                recommended_next_action=recommended_next_action,
            )
            metadata["browser_context_blocked_count"] = blocked_count
            self._maybe_apply_profile_quarantine(metadata, now=now)
            metadata["last_browser_validation_category"] = category
            metadata["last_browser_validation_final_category"] = category
            metadata["last_browser_validation_blocked_probe_reason"] = result.reason
            metadata["last_browser_validation_challenge_category"] = challenge_category
            metadata["last_browser_validation_recommended_next_action"] = recommended_next_action
            account.metadata_json = metadata
            account.status = DouyinAccountConnectionStatus.INVALID
            account.last_validation_status = challenge_state
            account.last_error_code = category
            account.last_error_message = result.reason
            self._apply_health_projection(account, now=now)
            return False, category
        if result.status == "login_required":
            metadata["last_browser_validation_category"] = "browser_validation_login_required"
            metadata["last_browser_validation_final_category"] = "browser_validation_login_required"
            account.metadata_json = metadata
            account.status = DouyinAccountConnectionStatus.EXPIRED
            account.last_validation_status = "browser_validation_login_required"
            account.last_error_code = "expired_session"
            account.last_error_message = result.reason
            self._apply_health_projection(account, now=now)
            return False, "browser_validation_login_required"
        if result.status in {"none", "stale", "invalid", "closed"}:
            category = "runtime_attach_failed" if validation_continued_after_reopen else "browser_validation_runtime_unavailable"
            if not has_saved_profile:
                category = "browser_validation_profile_unavailable"
            metadata["last_browser_validation_category"] = category
            metadata["last_browser_validation_final_category"] = category
            account.metadata_json = metadata
            if has_saved_profile:
                account.status = DouyinAccountConnectionStatus.INVALID
                account.last_validation_status = category
                account.last_error_code = "browser_validation_runtime_unavailable" if category == "runtime_attach_failed" else category
                account.last_error_message = result.reason
                self._apply_health_projection(account, now=now)
                return False, category
            return None
        if result.status == "uncertain" or has_saved_profile:
            metadata["last_browser_validation_category"] = "browser_validation_inconclusive"
            metadata["last_browser_validation_final_category"] = "browser_validation_inconclusive"
            account.metadata_json = metadata
            account.status = DouyinAccountConnectionStatus.INVALID
            account.last_validation_status = "browser_validation_inconclusive"
            account.last_error_code = "browser_validation_inconclusive"
            account.last_error_message = result.reason
            self._apply_health_projection(account, now=now)
            return False, "browser_validation_inconclusive"
        if has_saved_profile:
            return self._set_browser_validation_failure(
                account,
                metadata=metadata,
                now=now,
                category="browser_validation_failed_unknown",
                error_code="browser_validation_failed_unknown",
                reason=result.reason or result.status or "browser_validation_failed_unknown",
                context_status=result.status,
                runtime_context_id=result.runtime_context_id,
                auto_reopen_status=metadata.get("last_browser_validation_reopen_status") if isinstance(metadata.get("last_browser_validation_reopen_status"), str) else None,
                runtime_reattached=bool(metadata.get("last_browser_validation_runtime_reattached")),
                validation_continued=validation_continued_after_reopen,
            )
        return None

    def _browser_reopen_attach_failure_reason(
        self,
        *,
        account: DouyinAccountConnection,
        reopen_summary,
        expected_profile_id: str | None,
        expected_profile_path: str | None,
    ) -> str | None:
        if reopen_summary.account_connection_id != account.id:
            return "runtime_rebind_account_mismatch"
        if not douyin_browser_context_registry.profile_identity_matches(
            expected_profile_id=expected_profile_id,
            expected_profile_path=expected_profile_path,
            actual_profile_id=reopen_summary.browser_profile_id,
            actual_profile_path=reopen_summary.browser_profile_path,
        ):
            return "runtime_rebind_profile_mismatch"
        registry_summary = douyin_browser_context_registry.summary_for_account(account.id)
        if registry_summary.status != "active":
            return registry_summary.reason or f"runtime_rebind_summary_{registry_summary.status}"
        if registry_summary.runtime_context_id != reopen_summary.runtime_context_id:
            return "runtime_rebind_context_mismatch"
        return None

    def _start_browser_validation_attempt_metadata(
        self,
        account: DouyinAccountConnection,
        *,
        now: datetime,
    ) -> dict:
        metadata = dict(getattr(account, "metadata_json", None) or {})
        for key in (
            "last_browser_context_status",
            "last_browser_context_reason",
            "last_browser_validation_attach_first_attempted",
            "last_browser_validation_runtime_attach_status",
            "last_browser_validation_page_recovery_status",
            "last_browser_validation_auto_reopen_attempted",
            "last_browser_validation_auto_reopen_started_at",
            "last_browser_validation_reopen_status",
            "last_browser_validation_reopen_reason",
            "last_browser_validation_reopen_at",
            "last_browser_validation_runtime_reattached",
            "last_browser_validation_runtime_reattached_at",
            "last_browser_validation_reattached_context_id",
            "last_browser_validation_continued_after_reopen",
            "last_browser_validation_category",
            "last_browser_validation_final_category",
            "last_browser_validation_blocked_probe_reason",
            "last_browser_validation_challenge_category",
            "last_browser_validation_recommended_next_action",
        ):
            metadata.pop(key, None)
        metadata["last_browser_validation_attempt_id"] = str(uuid4())
        metadata["last_browser_validation_attempt_started_at"] = now.isoformat()
        metadata["last_browser_validation_auto_reopen_attempted"] = False
        metadata["last_browser_validation_runtime_reattached"] = False
        metadata["last_browser_validation_continued_after_reopen"] = False
        account.metadata_json = metadata
        return metadata

    def _classify_browser_validation_challenge(self, reason: str | None) -> tuple[str, str, str]:
        lowered = (reason or "").lower()
        if "captcha" in lowered or "验证码" in lowered or "滑块" in lowered:
            return "browser_validation_captcha_required", "captcha_required", "solve_captcha_in_browser_profile"
        if (
            "security" in lowered
            or "verify" in lowered
            or "challenge" in lowered
            or "安全验证" in lowered
            or "请完成验证" in lowered
            or "browser_context_blocked_response" in lowered
        ):
            return "browser_validation_challenge_required", "challenge_required", "complete_challenge_in_browser_profile"
        if "blocked" in lowered or "manual" in lowered:
            return "browser_validation_manual_verification_required", "manual_verification_required", "complete_manual_verification_in_browser_profile"
        return "browser_validation_manual_verification_required", "manual_verification_required", "complete_manual_verification_in_browser_profile"

    def _has_saved_browser_profile_metadata(self, metadata: dict) -> bool:
        return isinstance(metadata.get("browser_profile_id"), str) or isinstance(metadata.get("browser_profile_path"), str)

    def _is_challenge_actionable(self, metadata: dict, last_validation_status: str | None) -> bool:
        state = metadata.get("douyin_challenge_state")
        if state in {"challenge_waiting_for_manual_verification", "challenge_cooldown", "challenge_repeat_limit_reached"}:
            return True
        if last_validation_status in DOUYIN_CHALLENGE_VALIDATION_STATUSES:
            return True
        return metadata.get("last_browser_validation_final_category") in DOUYIN_CHALLENGE_VALIDATION_STATUSES

    def _saved_profile_identity(self, metadata: dict, account_id: UUID) -> tuple[str | None, str | None]:
        saved_profile_id = metadata.get("browser_profile_id") if isinstance(metadata.get("browser_profile_id"), str) else None
        saved_profile_path = metadata.get("browser_profile_path") if isinstance(metadata.get("browser_profile_path"), str) else None
        if not saved_profile_id and not saved_profile_path:
            return None, None
        return douyin_browser_context_registry.profile_identity_for_account(
            account_id,
            browser_profile_id=saved_profile_id,
            browser_profile_path=saved_profile_path,
        )

    def _challenge_postcheck_result_for(self, *, reason: str, valid: bool) -> str:
        if valid and reason == "browser_validation_success":
            return "challenge_postcheck_success"
        if reason == "challenge_cooldown_active":
            return "challenge_postcheck_cooldown_active"
        if reason in DOUYIN_CHALLENGE_VALIDATION_STATUSES or reason in DOUYIN_CHALLENGE_UNRESOLVED_STATES:
            return "challenge_postcheck_still_required"
        if reason == "runtime_rebind_profile_mismatch" or reason == "browser_validation_profile_mismatch":
            return "challenge_postcheck_profile_mismatch"
        if reason == "browser_validation_login_required":
            return "challenge_postcheck_login_required"
        if reason in {"browser_validation_runtime_unavailable", "browser_validation_profile_unavailable", "profile_reopen_failed", "runtime_attach_failed"}:
            return "challenge_postcheck_runtime_unavailable"
        if reason == "browser_validation_blocked":
            return "challenge_postcheck_blocked"
        if reason in {"browser_validation_inconclusive", "browser_context_blocked_retryable"}:
            return "challenge_postcheck_inconclusive"
        return "challenge_postcheck_failed_unknown"

    def _challenge_next_action_for_postcheck(self, post_check_result: str) -> str:
        if post_check_result == "challenge_postcheck_still_required":
            return "complete_challenge_in_browser_profile_then_mark_solved"
        if post_check_result == "challenge_postcheck_cooldown_active":
            return "wait_or_mark_challenge_solved_after_manual_completion"
        if post_check_result == "challenge_postcheck_profile_mismatch":
            return "reopen_saved_browser_profile_then_retry_recheck"
        if post_check_result == "challenge_postcheck_login_required":
            return "reconnect_saved_browser_profile_login"
        if post_check_result == "challenge_postcheck_runtime_unavailable":
            return "reopen_saved_browser_profile_then_retry_recheck"
        if post_check_result == "challenge_postcheck_blocked":
            return "review_browser_profile_block_before_retry"
        return "retry_browser_validation_after_manual_review"

    def _parse_metadata_datetime(self, value: object) -> datetime | None:
        if not isinstance(value, str) or not value:
            return None
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed

    def _challenge_count(self, metadata: dict) -> int:
        try:
            return max(0, int(metadata.get("douyin_challenge_count", 0)))
        except (TypeError, ValueError):
            return 0

    def _set_challenge_detected_metadata(
        self,
        metadata: dict,
        *,
        now: datetime,
        category: str,
        challenge_category: str,
        recommended_next_action: str,
    ) -> tuple[str, str]:
        count = self._challenge_count(metadata) + 1
        state = "challenge_waiting_for_manual_verification"
        next_action = recommended_next_action
        cooldown_until: datetime | None = None
        if count >= DOUYIN_CHALLENGE_REPEAT_LIMIT:
            state = "challenge_repeat_limit_reached"
            next_action = "wait_then_complete_challenge_in_browser_profile"
            cooldown_until = now + DOUYIN_CHALLENGE_COOLDOWN
        elif count > 1:
            state = "challenge_cooldown"
            next_action = "wait_then_complete_challenge_in_browser_profile"
            cooldown_until = now + DOUYIN_CHALLENGE_COOLDOWN
        metadata["douyin_challenge_state"] = state
        metadata["douyin_challenge_detected"] = True
        metadata["douyin_challenge_category"] = challenge_category
        metadata["douyin_challenge_validation_category"] = category
        metadata["douyin_challenge_count"] = count
        metadata["douyin_challenge_last_detected_at"] = now.isoformat()
        metadata["douyin_challenge_recommended_next_action"] = next_action
        metadata["douyin_challenge_recheck_resolved"] = False
        if cooldown_until is not None:
            metadata["douyin_challenge_cooldown_until"] = cooldown_until.isoformat()
        else:
            metadata.pop("douyin_challenge_cooldown_until", None)
        self._maybe_apply_profile_quarantine(metadata, now=now)
        return state, next_action

    def _clear_challenge_metadata(self, metadata: dict) -> None:
        for key in (
            "douyin_challenge_state",
            "douyin_challenge_detected",
            "douyin_challenge_category",
            "douyin_challenge_validation_category",
            "douyin_challenge_recommended_next_action",
            "douyin_challenge_cooldown_until",
            "douyin_challenge_last_detected_at",
            "douyin_challenge_last_solved_at",
            "douyin_challenge_count",
            "douyin_challenge_postcheck_result",
            "douyin_challenge_same_runtime_reused",
            "douyin_challenge_same_profile_reused",
            "douyin_challenge_runtime_reopened_for_recheck",
            "douyin_challenge_intake_ready_after_recheck",
        ):
            metadata.pop(key, None)
        metadata["douyin_challenge_recheck_resolved"] = True

    def _operator_confirmation_valid(self, confirmed_at: datetime | None, *, now: datetime) -> bool:
        if confirmed_at is None:
            return False
        if confirmed_at.tzinfo is None:
            confirmed_at = confirmed_at.replace(tzinfo=UTC)
        age = now - confirmed_at
        return timedelta(0) <= age <= DOUYIN_OPERATOR_CONFIRMED_READY_WINDOW

    def _browser_context_blocked_count(self, metadata: dict) -> int:
        try:
            return max(0, int(metadata.get("browser_context_blocked_count", 0)))
        except (TypeError, ValueError):
            return 0

    def _profile_quarantine_detected(self, metadata: dict) -> bool:
        return self._profile_quarantine_state(metadata) != "active_preferred"

    def _profile_quarantine_state(self, metadata: dict) -> str:
        state = metadata.get("douyin_profile_quarantine_state")
        if isinstance(state, str) and state in DOUYIN_PROFILE_QUARANTINE_STATES:
            return state
        if self._has_saved_browser_profile_metadata(metadata):
            if metadata.get("douyin_challenge_state") == "challenge_repeat_limit_reached":
                return "quarantined"
            if self._challenge_count(metadata) >= DOUYIN_PROFILE_QUARANTINE_CHALLENGE_THRESHOLD:
                return "quarantined"
            if self._browser_context_blocked_count(metadata) >= DOUYIN_PROFILE_QUARANTINE_BLOCKED_THRESHOLD:
                return "quarantined"
        return "active_preferred"

    def _profile_quarantine_reason(self, metadata: dict) -> str | None:
        reason = metadata.get("douyin_profile_quarantine_reason")
        if isinstance(reason, str) and reason:
            return reason
        if metadata.get("douyin_challenge_state") == "challenge_repeat_limit_reached":
            return "challenge_repeat_limit_reached"
        if self._challenge_count(metadata) >= DOUYIN_PROFILE_QUARANTINE_CHALLENGE_THRESHOLD:
            return "challenge_count_threshold_reached"
        if self._browser_context_blocked_count(metadata) >= DOUYIN_PROFILE_QUARANTINE_BLOCKED_THRESHOLD:
            return "browser_context_blocked_threshold_reached"
        return None

    def _profile_quarantine_recommended_next_action(self, metadata: dict) -> str | None:
        action = metadata.get("douyin_profile_quarantine_recommended_next_action")
        if isinstance(action, str) and action:
            return action
        if self._profile_quarantine_detected(metadata):
            return DOUYIN_PROFILE_QUARANTINE_RECOMMENDED_ACTION
        return None

    def _profile_quarantine_replaced_by_account_id(self, metadata: dict) -> UUID | None:
        value = metadata.get("douyin_profile_quarantine_replaced_by_account_id")
        if not isinstance(value, str) or not value:
            return None
        try:
            return UUID(value)
        except ValueError:
            return None

    def _profile_quarantine_blocks_primary_flow(self, metadata: dict) -> bool:
        return self._profile_quarantine_state(metadata) in DOUYIN_PROFILE_QUARANTINE_BLOCKING_STATES

    def _maybe_apply_profile_quarantine(self, metadata: dict, *, now: datetime) -> None:
        if not self._has_saved_browser_profile_metadata(metadata):
            return
        existing_state = metadata.get("douyin_profile_quarantine_state")
        if isinstance(existing_state, str) and existing_state in DOUYIN_PROFILE_QUARANTINE_BLOCKING_STATES:
            return
        reason = self._profile_quarantine_reason(metadata)
        if reason is None:
            return
        metadata["douyin_profile_quarantine_state"] = "quarantined"
        metadata["douyin_profile_quarantine_reason"] = reason
        metadata.setdefault("douyin_profile_quarantine_detected_at", now.isoformat())
        metadata["douyin_profile_quarantine_recommended_next_action"] = DOUYIN_PROFILE_QUARANTINE_RECOMMENDED_ACTION
        metadata["douyin_profile_quarantine_challenge_count"] = self._challenge_count(metadata)
        metadata["douyin_profile_quarantine_blocked_count"] = self._browser_context_blocked_count(metadata)

    def _profile_quarantine_preflight_block(self, account: DouyinAccountConnection, metadata: dict, *, browser_profile_exists: bool) -> DouyinFetchPreflightResult | None:
        self._maybe_apply_profile_quarantine(metadata, now=datetime.now(UTC))
        if not self._profile_quarantine_blocks_primary_flow(metadata):
            return None
        account.metadata_json = metadata
        return DouyinFetchPreflightResult(
            preflight_ran=True,
            preflight_result="failed",
            fetch_readiness_category="fetch_blocked_by_profile_quarantine",
            selected_fetch_path=None,
            browser_profile_available=browser_profile_exists,
            browser_reopen_attempted=False,
            preflight_failure_code="profile_quarantined",
            preflight_failure_message=DOUYIN_PROFILE_QUARANTINE_RECOMMENDATION,
            challenge_state=self._effective_challenge_state(metadata, now=datetime.now(UTC)),
            challenge_category=metadata.get("douyin_challenge_category") if isinstance(metadata.get("douyin_challenge_category"), str) else None,
            challenge_count=self._challenge_count(metadata),
            challenge_cooldown_until=self._parse_metadata_datetime(metadata.get("douyin_challenge_cooldown_until")),
            challenge_recommended_next_action=metadata.get("douyin_challenge_recommended_next_action") if isinstance(metadata.get("douyin_challenge_recommended_next_action"), str) else None,
            profile_quarantine_state=self._profile_quarantine_state(metadata),
            profile_quarantine_reason=self._profile_quarantine_reason(metadata),
            profile_quarantine_detected=True,
            profile_quarantine_recommended_next_action=self._profile_quarantine_recommended_next_action(metadata),
            profile_quarantine_blocks_primary_flow=True,
            profile_quarantine_replaced_by_account_id=self._profile_quarantine_replaced_by_account_id(metadata),
            profile_quarantine_clean_profile_recommendation=DOUYIN_PROFILE_QUARANTINE_RECOMMENDATION,
        )

    def _effective_challenge_state(self, metadata: dict, *, now: datetime) -> str | None:
        cooldown_active, state, _ = self._active_challenge_cooldown(metadata, now=now)
        if cooldown_active:
            return "challenge_cooldown_active"
        return state

    def _active_challenge_cooldown(self, metadata: dict, *, now: datetime) -> tuple[bool, str | None, datetime | None]:
        state = metadata.get("douyin_challenge_state")
        if state not in {"challenge_cooldown", "challenge_repeat_limit_reached"}:
            return False, state if isinstance(state, str) else None, None
        cooldown_until = self._parse_metadata_datetime(metadata.get("douyin_challenge_cooldown_until"))
        if cooldown_until is None or cooldown_until <= now:
            return False, state, cooldown_until
        return True, state, cooldown_until

    def _challenge_preflight_block(self, account: DouyinAccountConnection, metadata: dict, *, browser_profile_exists: bool) -> DouyinFetchPreflightResult | None:
        state = metadata.get("douyin_challenge_state")
        if state not in DOUYIN_CHALLENGE_UNRESOLVED_STATES:
            return None
        now = datetime.now(UTC)
        cooldown_active, _, cooldown_until = self._active_challenge_cooldown(metadata, now=now)
        if state in {"challenge_cooldown", "challenge_repeat_limit_reached"} and not cooldown_active and cooldown_until is not None:
            state = "challenge_waiting_for_manual_verification"
            cooldown_until = None
            metadata["douyin_challenge_state"] = state
            metadata.pop("douyin_challenge_cooldown_until", None)
            metadata["douyin_challenge_recommended_next_action"] = "complete_challenge_in_browser_profile_then_mark_solved"
            account.metadata_json = metadata
            self.invalidate_preflight_cache(account.id)
            self.db.commit()
        preflight_state = "challenge_cooldown_active" if cooldown_active else state
        category = metadata.get("douyin_challenge_category") if isinstance(metadata.get("douyin_challenge_category"), str) else None
        next_action = metadata.get("douyin_challenge_recommended_next_action") if isinstance(metadata.get("douyin_challenge_recommended_next_action"), str) else None
        if cooldown_active:
            next_action = "wait_or_mark_challenge_solved_after_manual_completion"
        return DouyinFetchPreflightResult(
            preflight_ran=True,
            preflight_result="failed",
            fetch_readiness_category="fetch_blocked_by_browser_challenge",
            selected_fetch_path=None,
            browser_profile_available=browser_profile_exists,
            browser_reopen_attempted=False,
            preflight_failure_code=preflight_state,
            preflight_failure_message=(
                f"Douyin challenge cooldown is active until {cooldown_until.isoformat()}. Complete the challenge in the saved browser profile, then use Mark challenge solved."
                if cooldown_active and cooldown_until is not None
                else "Douyin browser profile has an unresolved manual challenge. Complete it in the saved browser profile, mark it solved, then run post-challenge validation before Intake."
            ),
            challenge_state=preflight_state,
            challenge_category=category,
            challenge_count=self._challenge_count(metadata),
            challenge_cooldown_until=cooldown_until if cooldown_active or state in {"challenge_cooldown", "challenge_repeat_limit_reached"} else None,
            challenge_recommended_next_action=next_action,
        )

    def _set_browser_validation_failure(
        self,
        account: DouyinAccountConnection,
        *,
        metadata: dict,
        now: datetime,
        category: str,
        error_code: str,
        reason: str,
        context_status: str | None,
        runtime_context_id: str | None,
        auto_reopen_status: str | None,
        runtime_reattached: bool,
        validation_continued: bool,
    ) -> tuple[bool, str]:
        metadata["last_browser_validation_category"] = category
        metadata["last_browser_validation_final_category"] = category
        metadata["last_browser_context_status"] = context_status
        metadata["last_browser_context_reason"] = reason
        metadata["browser_context_id"] = runtime_context_id
        metadata["browser_context_checked_at"] = now.isoformat()
        metadata.setdefault("last_browser_validation_managed_runtime_status", "managed_runtime_missing")
        metadata.setdefault("last_browser_validation_profile_conflict_status", None)
        metadata["last_browser_validation_auto_reopen_attempted"] = auto_reopen_status is not None
        metadata["last_browser_validation_reopen_status"] = auto_reopen_status
        metadata["last_browser_validation_reopen_reason"] = reason
        metadata["last_browser_validation_runtime_reattached"] = runtime_reattached
        metadata["last_browser_validation_continued_after_reopen"] = validation_continued
        account.metadata_json = metadata
        account.status = DouyinAccountConnectionStatus.INVALID
        account.last_validation_status = category
        account.last_error_code = error_code
        account.last_error_message = reason
        self._apply_health_projection(account, now=now)
        return False, category

    def _is_retryable_browser_connect_validation_block(self, validation_source: str, blocked_count: int) -> bool:
        if validation_source == "connect_time":
            return True
        if validation_source == "connect_retry" and blocked_count < 2:
            return True
        return False

    def _refresh_session_from_live_browser_context(self, account: DouyinAccountConnection) -> None:
        settings = get_settings()
        if not settings.douyin_reuse_live_browser_for_fetch:
            return
        self._ensure_persistent_profile_context(account, purpose="fetch")
        result = douyin_browser_context_registry.refresh_session_artifacts(account.id)
        if not result.available or not result.cookie_header:
            return
        account.session_secret_blob = self._encode_session_cookie(result.cookie_header)
        if result.user_agent:
            account.user_agent = result.user_agent
        metadata = dict(getattr(account, "metadata_json", None) or {})
        metadata["last_browser_context_fetch_refresh_at"] = datetime.now(UTC).isoformat()
        metadata["last_browser_context_fetch_refresh_status"] = result.status
        metadata["browser_context_id"] = result.runtime_context_id
        account.metadata_json = metadata
        self.db.commit()

    def _ensure_persistent_profile_context(self, account: DouyinAccountConnection, *, purpose: str, force: bool = False):
        settings = get_settings()
        if purpose == "validation" and not force and not settings.douyin_prefer_browser_profile_for_validation:
            return None
        if purpose == "fetch" and not force and not settings.douyin_prefer_browser_profile_for_fetch:
            return None
        metadata = dict(getattr(account, "metadata_json", None) or {})
        browser_profile_id = metadata.get("browser_profile_id")
        browser_profile_path = metadata.get("browser_profile_path")
        if not isinstance(browser_profile_id, str):
            browser_profile_id = None
        if not isinstance(browser_profile_path, str):
            browser_profile_path = None
        if not browser_profile_id and not browser_profile_path:
            return None
        summary = douyin_browser_context_registry.open_profile_for_account(
            workspace_id=account.workspace_id,
            account_connection_id=account.id,
            browser_profile_id=browser_profile_id,
            browser_profile_path=browser_profile_path,
            user_agent=account.user_agent,
            proxy_url=account.proxy_url,
        )
        metadata["last_browser_profile_open_status"] = summary.status
        metadata["last_browser_profile_open_reason"] = summary.reason
        metadata["last_browser_profile_open_managed_runtime_status"] = getattr(summary, "managed_runtime_status", None)
        metadata["last_browser_profile_open_profile_conflict_status"] = getattr(summary, "profile_conflict_status", None)
        metadata["last_browser_profile_open_purpose"] = purpose
        metadata["last_browser_profile_open_checked_at"] = datetime.now(UTC).isoformat()
        if summary.runtime_context_id:
            metadata["browser_context_id"] = summary.runtime_context_id
        account.metadata_json = metadata
        return summary

    def _resolve_normalized_session_cookie(self, account: DouyinAccountConnection) -> str | None:
        decoded = self._decode_session_cookie(account.session_secret_blob)
        normalized_import = self._normalize_imported_session(
            decoded,
            explicit_user_agent=getattr(account, "user_agent", None),
            headers_json=getattr(account, "headers_json", None),
            enforce_cookie_strength=self._is_manual_import_account(account),
            allow_missing=True,
        )
        if normalized_import is None:
            return None
        if decoded != normalized_import.session_cookie:
            account.session_secret_blob = self._encode_session_cookie(normalized_import.session_cookie)
            if normalized_import.user_agent and not getattr(account, "user_agent", None):
                account.user_agent = normalized_import.user_agent
            if normalized_import.headers_json is not None:
                account.headers_json = normalized_import.headers_json
            self.db.commit()
        return normalized_import.session_cookie

    def _normalize_imported_session(
        self,
        value: str | None,
        *,
        explicit_user_agent: str | None,
        headers_json: dict | None = None,
        require_user_agent: bool = False,
        enforce_cookie_strength: bool = False,
        allow_missing: bool = False,
    ) -> NormalizedImportedSession | None:
        headers_copy = dict(headers_json) if isinstance(headers_json, dict) else None
        candidates = [value, self._cookie_from_headers(headers_copy)]
        normalized_cookie: str | None = None
        detected_format = "cookie_header"
        extracted_user_agent: str | None = explicit_user_agent.strip() if isinstance(explicit_user_agent, str) and explicit_user_agent.strip() else None
        for candidate in candidates:
            parsed = self._parse_imported_session_candidate(candidate)
            if parsed is None:
                continue
            normalized_cookie = parsed.session_cookie
            detected_format = parsed.detected_format
            headers_copy = parsed.headers_json if parsed.headers_json is not None else headers_copy
            if extracted_user_agent is None and parsed.user_agent:
                extracted_user_agent = parsed.user_agent
            break
        if normalized_cookie is None:
            if allow_missing:
                return None
            raise DouyinAccountError(
                "Imported session is missing a valid Cookie header.",
                code="imported_session_missing_cookie",
            )
        if headers_copy is None:
            headers_copy = {}
        if extracted_user_agent is None:
            extracted_user_agent = self._user_agent_from_headers(headers_copy)
        if extracted_user_agent:
            headers_copy["User-Agent"] = extracted_user_agent
        if require_user_agent and not extracted_user_agent:
            raise DouyinAccountError(
                "Imported account is missing a usable User-Agent.",
                code="imported_session_missing_user_agent",
            )
        cookie_strength = self._cookie_strength(normalized_cookie)
        if enforce_cookie_strength and cookie_strength == "thin":
            raise DouyinAccountError(
                "Imported session did not include strong authenticated Douyin cookies.",
                code="imported_session_cookie_too_thin",
            )
        return NormalizedImportedSession(
            session_cookie=normalized_cookie,
            user_agent=extracted_user_agent,
            detected_format=detected_format,
            headers_json=headers_copy or None,
        )

    def _parse_imported_session_candidate(self, value: str | None) -> NormalizedImportedSession | None:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if text.lower().startswith("cookie:"):
            text = text.split(":", 1)[1].strip()

        json_parsed = self._normalize_session_json_payload(text)
        if json_parsed is not None:
            return json_parsed

        normalized_pairs = [segment.strip() for segment in text.replace("\r", ";").replace("\n", ";").split(";") if segment.strip()]
        if not normalized_pairs:
            return None
        if not any("=" in segment for segment in normalized_pairs):
            raise DouyinAccountError(
                "Imported session payload did not contain any cookie name/value pairs.",
                code="imported_session_invalid",
            )
        return NormalizedImportedSession(
            session_cookie="; ".join(normalized_pairs),
            user_agent=None,
            detected_format="cookie_header",
            headers_json=None,
        )

    def _normalize_session_cookie_input(
        self,
        value: str | None,
        *,
        headers_json: dict | None = None,
        allow_missing: bool = False,
    ) -> str | None:
        normalized = self._normalize_imported_session(
            value,
            explicit_user_agent=None,
            headers_json=headers_json,
            require_user_agent=False,
            allow_missing=allow_missing,
        )
        return None if normalized is None else normalized.session_cookie

    def _normalize_session_json_payload(self, value: str) -> NormalizedImportedSession | None:
        stripped = value.strip()
        if not stripped or stripped[0] not in "[{":
            return None
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            raise DouyinAccountError(
                "Imported cookie export could not be parsed as JSON.",
                code="imported_session_cookie_parse_failed",
            )

        if isinstance(parsed, list):
            cookie_header = self._cookie_header_from_cookie_items(parsed)
            if cookie_header is None:
                return None
            return NormalizedImportedSession(
                session_cookie=cookie_header,
                user_agent=None,
                detected_format="json_cookie_array",
                headers_json=None,
            )
        if isinstance(parsed, dict):
            headers = dict(parsed.get("headers")) if isinstance(parsed.get("headers"), dict) else None
            cookie_header = self._cookie_from_headers(headers) if headers is not None else None
            if cookie_header:
                parsed_candidate = self._parse_imported_session_candidate(cookie_header)
                if parsed_candidate is None:
                    return None
                return NormalizedImportedSession(
                    session_cookie=parsed_candidate.session_cookie,
                    user_agent=self._user_agent_from_headers(headers),
                    detected_format="json_headers_export",
                    headers_json=headers,
                )
            direct_cookie = parsed.get("cookie") or parsed.get("Cookie")
            if isinstance(direct_cookie, str):
                parsed_candidate = self._parse_imported_session_candidate(direct_cookie)
                if parsed_candidate is None:
                    return None
                return NormalizedImportedSession(
                    session_cookie=parsed_candidate.session_cookie,
                    user_agent=self._user_agent_from_headers(headers),
                    detected_format="json_cookie_object",
                    headers_json=headers,
                )
            if isinstance(parsed.get("cookies"), list):
                cookie_header = self._cookie_header_from_cookie_items(parsed["cookies"])
                if cookie_header is None:
                    return None
                return NormalizedImportedSession(
                    session_cookie=cookie_header,
                    user_agent=self._user_agent_from_headers(headers),
                    detected_format="json_cookie_export",
                    headers_json=headers,
                )
            if isinstance(parsed.get("name"), str) and parsed.get("value") is not None:
                cookie_header = self._cookie_header_from_cookie_items([parsed])
                if cookie_header is None:
                    return None
                return NormalizedImportedSession(
                    session_cookie=cookie_header,
                    user_agent=self._user_agent_from_headers(headers),
                    detected_format="json_cookie_item",
                    headers_json=headers,
                )

        raise DouyinAccountError(
            "Imported session JSON did not contain any usable cookies.",
            code="imported_session_invalid",
        )

    def _cookie_header_from_cookie_items(self, items: list[object]) -> str | None:
        pairs: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            value = item.get("value")
            if not isinstance(name, str) or value is None:
                continue
            pairs.append(f"{name}={value}")
        if not pairs:
            raise DouyinAccountError(
                "Imported session JSON did not contain any cookie name/value pairs.",
                code="imported_session_invalid",
            )
        return "; ".join(pairs)

    def _cookie_strength(self, cookie_header: str) -> str:
        names = {
            segment.split("=", 1)[0].strip().lower()
            for segment in cookie_header.split(";")
            if "=" in segment
        }
        return "strong" if names & DOUYIN_IMPORTED_SESSION_STRONG_COOKIE_NAMES else "thin"

    def _looks_like_douyin_preflight_html(self, lowered_html: str) -> bool:
        return any(
            marker in lowered_html
            for marker in (
                "douyin",
                "__universal_data_for_rehydration__",
                "render_data",
                "sigi_state",
                "<html",
            )
        )

    def _manual_import_preflight_code_for_account(
        self,
        account: DouyinAccountConnection,
        *,
        valid: bool,
    ) -> str:
        if valid:
            return "usable_for_fetch"
        code = getattr(account, "last_error_code", None)
        if code:
            return code
        reason = getattr(account, "last_validation_status", None)
        if isinstance(reason, str) and reason:
            return self._normalize_validation_status(reason)
        return "unknown_validation_failure"

    def _manual_import_preflight_result(
        self,
        *,
        code: str,
        detected_format: str | None,
        cookie_strength: str | None,
        checked_at: datetime | None,
    ) -> ManualImportPreflightResult:
        summary_map: dict[str, tuple[str, str, str, bool]] = {
            "imported_session_missing_cookie": (
                "needs_fix",
                "Imported session is missing a valid Cookie header.",
                "Reimport a full Cookie header or browser cookie export before using this account.",
                False,
            ),
            "imported_session_cookie_parse_failed": (
                "needs_fix",
                "Imported cookie export could not be parsed.",
                "Paste a valid Cookie header or a valid JSON cookie export from the signed-in browser.",
                False,
            ),
            "imported_session_missing_user_agent": (
                "needs_fix",
                "Imported session is missing a usable User-Agent.",
                "Reimport the session with the same browser User-Agent used for the logged-in request.",
                False,
            ),
            "imported_session_cookie_too_thin": (
                "needs_fix",
                "Imported session parsed, but it does not include strong authenticated Douyin cookies.",
                "Reimport a fuller logged-in cookie export that includes account session cookies such as sessionid or sid_guard.",
                False,
            ),
            "login_required": (
                "retryable",
                "Cookie export parsed, but Douyin still requires login.",
                "Reimport a fresh logged-in session or reopen the saved browser profile and validate again.",
                False,
            ),
            "expired_session": (
                "retryable",
                "Imported session looks expired or redirected back to login.",
                "Capture a fresh logged-in session and validate it again before using Intake.",
                False,
            ),
            "blocked_response": (
                "blocked",
                "Douyin returned a blocked response for this imported session.",
                "Retry from a different network or proxy, or switch to a browser-backed account for this source.",
                False,
            ),
            "validation_transport_error": (
                "retryable",
                "Validation could not reach Douyin reliably.",
                "Check proxy or network settings, then retry validation before using this account.",
                False,
            ),
            "transport_error": (
                "retryable",
                "Validation could not reach Douyin reliably.",
                "Check proxy or network settings, then retry validation before using this account.",
                False,
            ),
            "parse_failed": (
                "needs_fix",
                "Douyin responded, but the imported session did not pass fetch preflight cleanly.",
                "Reimport a stronger session or use a browser-backed account if this profile still fails preflight.",
                False,
            ),
            "usable_for_fetch": (
                "usable",
                "Imported session passed fetch preflight.",
                "This account is ready for live fetch and can be used in Intake now.",
                True,
            ),
            "unknown_validation_failure": (
                "retryable",
                "Imported session validation failed for an unknown reason.",
                "Validate again or reimport a fresh session before using this account in Intake.",
                False,
            ),
        }
        normalized_code = code if code in summary_map else "unknown_validation_failure"
        outcome, summary, next_action, fetch_usable = summary_map[normalized_code]
        return ManualImportPreflightResult(
            code=normalized_code,
            outcome=outcome,
            summary=summary,
            next_action=next_action,
            fetch_usable=fetch_usable,
            detected_format=detected_format,
            cookie_strength=cookie_strength,
            checked_at=checked_at,
        )

    def _manual_import_preflight_summary(
        self,
        account: DouyinAccountConnection,
    ) -> DouyinManualImportPreflightSummary | None:
        if not self._is_manual_import_account(account):
            return None
        metadata = dict(getattr(account, "metadata_json", None) or {})
        payload = metadata.get("manual_import_preflight")
        if not isinstance(payload, dict):
            payload = self._manual_import_preflight_result(
                code=self._manual_import_preflight_code_for_account(account, valid=account.status == DouyinAccountConnectionStatus.ACTIVE),
                detected_format=metadata.get("session_import_format") if isinstance(metadata.get("session_import_format"), str) else None,
                cookie_strength=self._cookie_strength(self._decode_session_cookie(account.session_secret_blob) or "") if account.session_secret_blob else None,
                checked_at=account.last_validated_at,
            ).__dict__
        return DouyinManualImportPreflightSummary.model_validate(payload)

    def _update_manual_import_preflight(
        self,
        account: DouyinAccountConnection,
        *,
        code: str,
        checked_at: datetime | None,
    ) -> None:
        if not self._is_manual_import_account(account):
            return
        metadata = dict(getattr(account, "metadata_json", None) or {})
        detected_format = metadata.get("session_import_format") if isinstance(metadata.get("session_import_format"), str) else None
        cookie_header = self._decode_session_cookie(account.session_secret_blob)
        cookie_strength = self._cookie_strength(cookie_header) if cookie_header else None
        payload = self._manual_import_preflight_result(
            code=code,
            detected_format=detected_format,
            cookie_strength=cookie_strength,
            checked_at=checked_at,
        )
        metadata["manual_import_preflight"] = {
            "code": payload.code,
            "outcome": payload.outcome,
            "summary": payload.summary,
            "next_action": payload.next_action,
            "fetch_usable": payload.fetch_usable,
            "source_type": payload.source_type,
            "detected_format": payload.detected_format,
            "cookie_strength": payload.cookie_strength,
            "checked_at": payload.checked_at.isoformat() if payload.checked_at else None,
        }
        account.metadata_json = metadata

    def _is_manual_import_metadata(self, metadata_json: dict | None) -> bool:
        if not isinstance(metadata_json, dict):
            return False
        return metadata_json.get("connection_source") == "manual_import"

    def _is_manual_import_account(self, account: DouyinAccountConnection) -> bool:
        return self._is_manual_import_metadata(getattr(account, "metadata_json", None))

    def _cookie_from_headers(self, headers_json: dict | None) -> str | None:
        if not isinstance(headers_json, dict):
            return None
        value = headers_json.get("Cookie")
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = headers_json.get("cookie")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _user_agent_from_headers(self, headers_json: dict | None) -> str | None:
        if not isinstance(headers_json, dict):
            return None
        value = headers_json.get("User-Agent")
        if isinstance(value, str) and value.strip():
            return value.strip()
        value = headers_json.get("user-agent")
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    def _encode_session_cookie(self, value: str) -> str:
        settings = get_settings()
        return DouyinSessionSecretEnvelope(
            key_ref=getattr(settings, "douyin_secret_encryption_key_ref", None)
        ).encrypt(value)

    def _decode_session_cookie(self, value: str | None) -> str | None:
        settings = get_settings()
        return DouyinSessionSecretEnvelope(
            key_ref=getattr(settings, "douyin_secret_encryption_key_ref", None)
        ).decrypt(value)

    def _preview_secret(self, value: str | None) -> str | None:
        if not value:
            return None
        return f"{value[:4]}...{value[-4:]}" if len(value) > 8 else "****"

    def _status_from_adapter_error(self, exc: SourceAdapterError) -> DouyinAccountConnectionStatus:
        if exc.code == SourceAdapterErrorCode.RATE_LIMITED:
            return DouyinAccountConnectionStatus.BLOCKED
        return DouyinAccountConnectionStatus.INVALID

    def _classify_validation_adapter_error(self, exc: SourceAdapterError) -> str:
        lowered = exc.message.lower()
        if exc.code == SourceAdapterErrorCode.RATE_LIMITED:
            return "blocked_response"
        if "login" in lowered or "passport" in lowered or "expired" in lowered:
            return "login_required"
        if "blocked" in lowered or "captcha" in lowered or "security" in lowered or "challenge" in lowered:
            return "blocked_response"
        if "profile/video metadata" in lowered or "did not expose" in lowered:
            return "parse_failed"
        if "network" in lowered or "timeout" in lowered or "http " in lowered or "transport" in lowered:
            return "validation_transport_error"
        return "unknown_validation_failure"

    def _apply_health_projection(self, account: DouyinAccountConnection, *, now: datetime | None = None) -> None:
        now = now or datetime.now(UTC)
        if account.status == DouyinAccountConnectionStatus.ACTIVE:
            successful = account.last_successful_validation_at or now
            account.next_validation_due_at = successful + DOUYIN_ACCOUNT_FRESH_WINDOW
        elif account.status in {DouyinAccountConnectionStatus.INVALID, DouyinAccountConnectionStatus.EXPIRED, DouyinAccountConnectionStatus.BLOCKED}:
            account.next_validation_due_at = now
        elif account.status == DouyinAccountConnectionStatus.DISABLED:
            account.next_validation_due_at = None

        health = self.health_summary(account, now=now)
        account.health_status = health.health_status
        account.warning_level = health.warning_level
        account.expires_at = health.expires_at
        account.warning_summary_json = health.warning_summary

    def _normalize_validation_status(self, reason: str) -> str:
        lowered = reason.lower()
        if lowered in {
            "usable_for_fetch",
            "imported_session_missing_cookie",
            "imported_session_cookie_parse_failed",
            "imported_session_missing_user_agent",
            "imported_session_cookie_too_thin",
            "login_required",
            "blocked_response",
            "validation_transport_error",
            "parse_failed",
            "unknown_validation_failure",
            "browser_validation_success",
            "browser_validation_inconclusive",
            "browser_validation_runtime_reopened",
            "browser_validation_captcha_required",
            "browser_validation_challenge_required",
            "browser_validation_manual_verification_required",
            "challenge_waiting_for_manual_verification",
            "challenge_recently_solved_pending_recheck",
            "challenge_cooldown",
            "challenge_cooldown_active",
            "challenge_repeat_limit_reached",
            "challenge_recheck_required",
            "runtime_rebind_profile_mismatch",
            "browser_validation_profile_mismatch",
            "manual_verification_required",
            "browser_validation_blocked",
            "browser_validation_login_required",
            "browser_validation_runtime_unavailable",
            "browser_validation_profile_unavailable",
            "browser_validation_failed_unknown",
            "profile_reopen_failed",
            "runtime_attach_failed",
            "captcha_required",
        }:
            return lowered
        if "cookie export could not be parsed" in lowered:
            return "imported_session_cookie_parse_failed"
        if "missing_session" in lowered or "valid cookie header" in lowered or "usable cookies" in lowered:
            return "imported_session_missing_cookie"
        if "usable user-agent" in lowered:
            return "imported_session_missing_user_agent"
        if "strong authenticated douyin cookies" in lowered:
            return "imported_session_cookie_too_thin"
        if "imported session" in lowered and "invalid" in lowered:
            return "imported_session_invalid"
        if "parse_failed" in lowered or "did not pass fetch preflight" in lowered:
            return "parse_failed"
        if "expired" in lowered or "login" in lowered or "passport" in lowered:
            return "login_required"
        if "blocked" in lowered or "captcha" in lowered or "rate" in lowered or "security" in lowered:
            return "blocked_response"
        if "proxy" in lowered:
            return "proxy_failure"
        if "network" in lowered or "timeout" in lowered or "transport" in lowered:
            return "validation_transport_error"
        if "invalid" in lowered:
            return "invalid_session"
        return "unknown_validation_failure"

    def _safe_validation_url(self, validation_url: str | None) -> str:
        if not validation_url:
            return "https://www.douyin.com/"
        parsed = urlparse(validation_url)
        host = parsed.hostname.lower() if parsed.hostname else ""
        if parsed.scheme not in {"http", "https"} or not (host == "douyin.com" or host.endswith(".douyin.com")):
            raise DouyinAccountError("validation_url must be a Douyin URL")
        return validation_url
