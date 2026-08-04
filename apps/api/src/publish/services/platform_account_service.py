from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
from pathlib import Path
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.settings import Settings, get_settings
from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.models.foundation import Workspace
from src.models.publish import PlatformAccount
from src.publish.services.platform_credential_store import (
    PLATFORM_CREDENTIAL_REFERENCE_PREFIX,
    PlatformCredentialStore,
)
from src.publish.types import PlatformAccountConfig
from src.schemas.publish import PlatformAccountCreateRequest, PlatformAccountUpdateRequest


class PlatformAccountError(ValueError):
    pass


SERVER_OWNED_FACEBOOK_METADATA_KEYS = frozenset(
    {
        "credential_source",
        "facebook_page_picture_url",
        "facebook_page_tasks",
        "facebook_publish_capability_verified",
        "facebook_publish_capability_verified_at",
        "facebook_verified_publish_scopes",
        "facebook_oauth_connection_id",
        "facebook_oauth_connected_at",
        "facebook_oauth_requested_scopes",
        "facebook_publish_last_safety_error_code",
        "facebook_publish_last_safety_error_at",
    }
)
OAUTH_MANAGED_METADATA_KEYS = SERVER_OWNED_FACEBOOK_METADATA_KEYS | frozenset(
    {
        "graph_api_version",
        "metrics_insights_enabled",
        "facebook_insights_token_type",
        "facebook_insights_verified_external_account_id",
        "facebook_verified_insights_scopes",
        "facebook_insights_scopes_verified_at",
    }
)
SYSTEM_HOLD_PREFIXES = ("FACEBOOK_OAUTH_CAPABILITY_MISSING:", "FACEBOOK_SAFETY_HOLD:")


class PlatformAccountService:
    def __init__(self, db: Session, *, settings: Settings | None = None):
        self.db = db
        self.settings = settings or get_settings()

    def create_account(self, request: PlatformAccountCreateRequest) -> PlatformAccount:
        workspace_id = request.workspace_id or self._default_workspace_id()
        account = PlatformAccount(
            workspace_id=workspace_id,
            platform=request.platform,
            display_name=request.display_name,
            external_account_id=request.external_account_id,
            token_reference=request.token_reference,
            status=request.status,
            priority=request.priority,
            is_on_hold=request.is_on_hold,
            hold_reason=request.hold_reason,
            cooldown_until=request.cooldown_until,
            allowed_niches_json=request.allowed_niches_json,
            metadata_json=self._sanitize_create_metadata(request.metadata_json),
            routing_notes=request.routing_notes,
            notes=request.notes,
        )
        self.db.add(account)
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PlatformAccountError("Facebook Page is already configured in this workspace") from exc
        self.db.refresh(account)
        return account

    def list_accounts(
        self,
        *,
        platform: PublishTargetPlatform | None = None,
        status: PlatformAccountStatus | None = None,
    ) -> list[PlatformAccount]:
        stmt = select(PlatformAccount).order_by(PlatformAccount.created_at.desc())
        if platform is not None:
            stmt = stmt.where(PlatformAccount.platform == platform)
        if status is not None:
            stmt = stmt.where(PlatformAccount.status == status)
        return list(self.db.scalars(stmt))

    def get_account(self, account_id: UUID) -> PlatformAccount:
        account = self.db.get(PlatformAccount, account_id)
        if account is None:
            raise PlatformAccountError("Platform account not found")
        return account

    def update_account(self, account_id: UUID, request: PlatformAccountUpdateRequest) -> PlatformAccount:
        account = self.get_account(account_id)
        provided_fields = request.model_fields_set
        oauth_managed = self._is_oauth_managed(account)
        if oauth_managed:
            for field in ("display_name", "external_account_id", "token_reference"):
                if field in provided_fields and getattr(request, field) != getattr(account, field):
                    raise PlatformAccountError(
                        "OAuth-managed Page identity and credential must be changed through Facebook reconnect"
                    )
        system_hold = str(account.hold_reason or "").startswith(SYSTEM_HOLD_PREFIXES)
        if system_hold:
            if "status" in provided_fields and request.status == PlatformAccountStatus.ACTIVE:
                raise PlatformAccountError("Reconnect Facebook before clearing a system safety hold")
            if "is_on_hold" in provided_fields and request.is_on_hold is False:
                raise PlatformAccountError("Reconnect Facebook before clearing a system safety hold")
            if "hold_reason" in provided_fields and request.hold_reason != account.hold_reason:
                raise PlatformAccountError("System safety hold reason is server-managed")
        current_cooldown = account.cooldown_until
        if current_cooldown is not None:
            if current_cooldown.tzinfo is None or current_cooldown.utcoffset() is None:
                current_cooldown = current_cooldown.replace(tzinfo=UTC)
            requested_cooldown = request.cooldown_until
            if requested_cooldown is not None and (
                requested_cooldown.tzinfo is None or requested_cooldown.utcoffset() is None
            ):
                requested_cooldown = requested_cooldown.replace(tzinfo=UTC)
            if (
                current_cooldown > datetime.now(UTC)
                and "cooldown_until" in provided_fields
                and (requested_cooldown is None or requested_cooldown < current_cooldown)
            ):
                raise PlatformAccountError("An active Facebook safety cooldown cannot be shortened")
        for field in [
            "display_name",
            "external_account_id",
            "token_reference",
            "status",
            "priority",
            "is_on_hold",
            "hold_reason",
            "cooldown_until",
            "allowed_niches_json",
            "routing_notes",
            "notes",
        ]:
            if field in provided_fields:
                setattr(account, field, getattr(request, field))
        if "metadata_json" in provided_fields:
            incoming_metadata = dict(request.metadata_json or {})
            if oauth_managed:
                existing_metadata = dict(account.metadata_json or {})
                for key in OAUTH_MANAGED_METADATA_KEYS:
                    if key in existing_metadata:
                        incoming_metadata[key] = existing_metadata[key]
                    else:
                        incoming_metadata.pop(key, None)
            else:
                for key in SERVER_OWNED_FACEBOOK_METADATA_KEYS:
                    incoming_metadata.pop(key, None)
            account.metadata_json = incoming_metadata
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise PlatformAccountError("Facebook Page is already configured in this workspace") from exc
        self.db.refresh(account)
        return account

    def resolve_config(
        self,
        account_id: UUID,
        *,
        require_active: bool = True,
    ) -> PlatformAccountConfig:
        account = self.get_account(account_id)
        if require_active and account.status != PlatformAccountStatus.ACTIVE:
            raise PlatformAccountError("Platform account is not ACTIVE")
        token_reference = account.token_reference or "FACEBOOK_PAGE_ACCESS_TOKEN"
        access_token = self._resolve_access_token(token_reference, account=account)
        if not access_token:
            raise PlatformAccountError(f"Missing access token env var: {token_reference}")
        graph_version = "v20.0"
        if isinstance(account.metadata_json, dict):
            graph_version = str(account.metadata_json.get("graph_api_version") or graph_version)
        return PlatformAccountConfig(
            platform_account_id=account.id,
            platform=account.platform,
            page_id=account.external_account_id,
            display_name=account.display_name,
            access_token=access_token,
            graph_api_version=graph_version,
        )

    def facebook_setup_check(self, account_id: UUID) -> dict:
        """Validate one Facebook Page setup without network I/O or token exposure."""

        account = self.get_account(account_id)
        metadata = account.metadata_json or {}
        now = datetime.now(UTC)
        checks: list[dict] = []

        def check(code: str, passed: bool, message: str, *, blocking: bool = True) -> None:
            checks.append(
                {
                    "code": code,
                    "passed": bool(passed),
                    "blocking": blocking and not bool(passed),
                    "message": message,
                }
            )

        page_id = str(account.external_account_id or "").strip()
        token_reference = self._normalize_token_reference(str(account.token_reference or ""))
        verified_scopes = {
            str(value).strip()
            for value in (metadata.get("facebook_verified_insights_scopes") or [])
            if str(value).strip()
        }
        verified_at = self._parse_aware_datetime(
            metadata.get("facebook_insights_scopes_verified_at")
        )
        publish_verified_at = self._parse_aware_datetime(
            metadata.get("facebook_publish_capability_verified_at")
        )
        publish_scopes = {
            str(value).strip()
            for value in (metadata.get("facebook_verified_publish_scopes") or [])
            if str(value).strip()
        }
        page_tasks = {
            str(value).strip().upper()
            for value in (metadata.get("facebook_page_tasks") or [])
            if str(value).strip()
        }

        check("account_platform", account.platform == PublishTargetPlatform.FACEBOOK_REELS, "Account platform is FACEBOOK_REELS")
        check("account_active", account.status == PlatformAccountStatus.ACTIVE, "Account status is ACTIVE")
        check("account_not_on_hold", not account.is_on_hold, "Account is not on manual hold")
        check("account_not_in_cooldown", account.cooldown_until is None or account.cooldown_until <= now, "Account has no active cooldown")
        check("page_identity", bool(page_id) and not self._looks_placeholder(page_id), "Facebook Page id is configured and not a placeholder")
        safe_reference = self.is_safe_token_reference(token_reference)
        check("token_reference", safe_reference, "Token reference is a safe environment name or encrypted credential reference")
        check("token_available", bool(token_reference) and bool(self._resolve_access_token(token_reference, account=account)), "The server can resolve the configured token reference")
        check(
            "publish_capability",
            metadata.get("facebook_publish_capability_verified") is True,
            "Facebook Page publish capability is verified through OAuth",
        )
        check(
            "publish_scope",
            "pages_manage_posts" in publish_scopes,
            "OAuth grant includes pages_manage_posts",
        )
        check(
            "publish_page_task",
            "CREATE_CONTENT" in page_tasks,
            "Facebook Page tasks include CREATE_CONTENT",
        )
        check(
            "publish_capability_fresh",
            publish_verified_at is not None
            and now
            - timedelta(days=max(1, int(self.settings.facebook_publish_capability_max_age_days)))
            <= publish_verified_at
            <= now + timedelta(minutes=5),
            "Publish capability verification is fresh",
        )
        check("page_token_type", metadata.get("facebook_insights_token_type") == "PAGE_ACCESS_TOKEN", "Token type is attested as PAGE_ACCESS_TOKEN")
        check("insights_capability", metadata.get("metrics_insights_enabled") is True, "Facebook Insights capability is enabled", blocking=False)
        check("verified_page_binding", metadata.get("facebook_insights_verified_external_account_id") == page_id, "Insights verification is bound to this Page id", blocking=False)
        check("verified_scopes", {"read_insights", "pages_read_engagement"}.issubset(verified_scopes), "Required Insights scopes are attested", blocking=False)
        check(
            "scope_verification_fresh",
            verified_at is not None and now - timedelta(days=30) <= verified_at <= now + timedelta(minutes=5),
            "Scope verification is timezone-aware and no older than 30 days",
            blocking=False,
        )
        check("graph_api_version", bool(re.fullmatch(r"v\d+\.\d+", str(metadata.get("graph_api_version") or ""))), "Graph API version uses v<major>.<minor>")
        check(
            "media_reference_source",
            metadata.get("facebook_insights_object_id_source")
            in {"external_publish_id", "external_media_id", "external_reel_id"},
            "A supported Facebook media-id source is selected",
        )
        blockers = [item["code"] for item in checks if item["blocking"]]
        return {
            "platform_account_id": account.id,
            "ready_for_publication_setup": not blockers,
            "network_used": False,
            "token_value_exposed": False,
            "checks": checks,
            "blocker_codes": blockers,
        }

    def _default_workspace_id(self) -> UUID:
        workspace = self.db.scalar(select(Workspace).order_by(Workspace.created_at.asc()).limit(1))
        if workspace is None:
            raise PlatformAccountError("Default workspace not found")
        return workspace.id

    @staticmethod
    def _sanitize_create_metadata(metadata: dict | None) -> dict | None:
        if metadata is None:
            return None
        sanitized = dict(metadata)
        for key in SERVER_OWNED_FACEBOOK_METADATA_KEYS:
            sanitized.pop(key, None)
        return sanitized

    @staticmethod
    def _is_oauth_managed(account: PlatformAccount) -> bool:
        metadata = account.metadata_json or {}
        return str(account.token_reference or "").startswith(
            PLATFORM_CREDENTIAL_REFERENCE_PREFIX
        ) or metadata.get("credential_source") == "META_OAUTH"

    def _resolve_access_token(self, token_reference: str, *, account: PlatformAccount | None = None) -> str | None:
        token_reference = self._normalize_token_reference(token_reference)
        if token_reference.startswith(PLATFORM_CREDENTIAL_REFERENCE_PREFIX):
            if account is None:
                return None
            return PlatformCredentialStore(
                self.db,
                settings=self.settings,
            ).resolve(token_reference, account=account)
        access_token = os.environ.get(token_reference)
        if access_token:
            return access_token

        for env_path in self._candidate_env_paths():
            token = self._read_env_value(env_path, token_reference)
            if token:
                return token
        return None

    def resolve_access_token(self, account: PlatformAccount) -> str | None:
        """Resolve one account credential without exposing it through an API schema."""

        return self._resolve_access_token(account.token_reference or "", account=account)

    @staticmethod
    def _normalize_token_reference(reference: str) -> str:
        value = reference.strip()
        return value[4:] if value.lower().startswith("env:") else value

    @classmethod
    def is_safe_token_reference(cls, reference: str) -> bool:
        """Validate opaque credential references without resolving or exposing a token."""

        value = cls._normalize_token_reference(reference)
        return bool(re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", value)) or (
            value.startswith(PLATFORM_CREDENTIAL_REFERENCE_PREFIX)
            and PlatformCredentialStore.parse_reference(value) is not None
        )

    def _candidate_env_paths(self) -> list[Path]:
        paths = [Path.cwd() / ".env", Path(__file__).resolve().parents[3] / ".env"]
        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            resolved = path.resolve()
            if resolved not in seen:
                unique.append(resolved)
                seen.add(resolved)
        return unique

    def _read_env_value(self, env_path: Path, key: str) -> str | None:
        if not env_path.exists():
            return None
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export ") :].strip()
            name, value = line.split("=", 1)
            if name.strip() != key:
                continue
            return value.strip().strip('"').strip("'") or None
        return None

    @staticmethod
    def _parse_aware_datetime(raw: object) -> datetime | None:
        if not raw:
            return None
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(UTC)

    @staticmethod
    def _looks_placeholder(raw: object) -> bool:
        value = str(raw or "").strip().lower()
        return not value or any(
            marker in value
            for marker in ("local", "demo", "fixture", "example", "invalid", "mock", "test")
        )
