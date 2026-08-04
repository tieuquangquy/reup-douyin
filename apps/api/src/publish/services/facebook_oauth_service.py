from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import json
import re
import secrets
from typing import Protocol
from urllib.parse import urlencode
from uuid import UUID, uuid4

import requests
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.core.settings import Settings
from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.models.publish import PlatformAccount, PlatformIntegrationConfiguration, PlatformOAuthSession
from src.publish.services.platform_account_service import PlatformAccountService
from src.publish.services.platform_credential_store import PlatformCredentialStore
from src.publish.services.platform_credential_key_store import (
    PlatformCredentialKeyStoreError,
    resolve_platform_credential_key_ref,
)
from src.publish.services.platform_secret_envelope import PlatformSecretEnvelope


FACEBOOK_PROVIDER = "FACEBOOK"
FACEBOOK_OAUTH_PENDING = "AUTHORIZATION_PENDING"
FACEBOOK_OAUTH_PAGE_SELECTION = "PAGE_SELECTION_REQUIRED"
FACEBOOK_OAUTH_COMPLETED = "COMPLETED"
FACEBOOK_OAUTH_FAILED = "FAILED"
FACEBOOK_OAUTH_EXPIRED = "EXPIRED"
FACEBOOK_OAUTH_SCOPE_ALLOWLIST = frozenset(
    {
        "pages_show_list",
        "pages_read_engagement",
        "read_insights",
        "pages_manage_posts",
    }
)
FACEBOOK_REQUIRED_PUBLISH_SCOPES = frozenset(
    {"pages_show_list", "pages_manage_posts"}
)
FACEBOOK_REQUIRED_PUBLISH_TASK = "CREATE_CONTENT"
FACEBOOK_OAUTH_CAPABILITY_HOLD_PREFIX = "FACEBOOK_OAUTH_CAPABILITY_MISSING:"
FACEBOOK_SAFETY_HOLD_PREFIX = "FACEBOOK_SAFETY_HOLD:"


class FacebookOAuthError(ValueError):
    def __init__(self, code: str, message: str, *, http_status: int = 422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status


class FacebookOAuthTransport(Protocol):
    def exchange_code(self, code: str) -> str: ...

    def exchange_long_lived_user_token(self, short_lived_token: str) -> str: ...

    def fetch_granted_scopes(self, user_token: str) -> set[str]: ...

    def fetch_pages(self, user_token: str) -> list[dict]: ...


class RequestsFacebookOAuthTransport:
    """Small Meta Graph boundary; request payloads and tokens are never logged."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.base_url = f"https://graph.facebook.com/{settings.facebook_graph_api_version}"
        self.timeout = max(1.0, float(settings.facebook_oauth_request_timeout_seconds))

    def exchange_code(self, code: str) -> str:
        payload = self._post(
            "/oauth/access_token",
            data={
                "client_id": self.settings.facebook_app_id,
                "client_secret": self.settings.facebook_app_secret,
                "redirect_uri": self.settings.facebook_oauth_redirect_uri,
                "code": code,
            },
            operation="authorization code exchange",
        )
        return self._require_token(payload, "authorization code exchange")

    def exchange_long_lived_user_token(self, short_lived_token: str) -> str:
        payload = self._post(
            "/oauth/access_token",
            data={
                "grant_type": "fb_exchange_token",
                "client_id": self.settings.facebook_app_id,
                "client_secret": self.settings.facebook_app_secret,
                "fb_exchange_token": short_lived_token,
            },
            operation="long-lived token exchange",
        )
        return self._require_token(payload, "long-lived token exchange")

    def fetch_granted_scopes(self, user_token: str) -> set[str]:
        payload = self._get(
            "/me/permissions",
            token=user_token,
            operation="permission discovery",
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return set()
        return {
            str(row.get("permission"))
            for row in rows
            if isinstance(row, dict)
            and row.get("status") == "granted"
            and row.get("permission")
        }

    def fetch_pages(self, user_token: str) -> list[dict]:
        payload = self._get(
            "/me/accounts",
            token=user_token,
            params={"fields": "id,name,access_token,tasks,picture.type(large)", "limit": "100"},
            operation="Page discovery",
        )
        rows = payload.get("data") if isinstance(payload, dict) else None
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []

    def _post(self, path: str, *, data: dict, operation: str) -> dict:
        try:
            response = requests.post(
                self.base_url + path,
                data=data,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise FacebookOAuthError("facebook_oauth_unreachable", f"Meta {operation} could not be reached", http_status=502) from exc
        return self._decode_response(response, operation)

    def _get(self, path: str, *, token: str, operation: str, params: dict | None = None) -> dict:
        try:
            response = requests.get(
                self.base_url + path,
                params=params,
                headers={"Accept": "application/json", "Authorization": f"Bearer {token}"},
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise FacebookOAuthError("facebook_oauth_unreachable", f"Meta {operation} could not be reached", http_status=502) from exc
        return self._decode_response(response, operation)

    @staticmethod
    def _decode_response(response: requests.Response, operation: str) -> dict:
        try:
            payload = response.json()
        except ValueError as exc:
            raise FacebookOAuthError("facebook_oauth_invalid_response", f"Meta {operation} returned an invalid response", http_status=502) from exc
        if not response.ok or not isinstance(payload, dict) or isinstance(payload.get("error"), dict):
            raise FacebookOAuthError("facebook_oauth_rejected", f"Meta {operation} was rejected", http_status=502)
        return payload

    @staticmethod
    def _require_token(payload: dict, operation: str) -> str:
        token = payload.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise FacebookOAuthError("facebook_oauth_token_missing", f"Meta {operation} did not return a token", http_status=502)
        return token.strip()


class FacebookOAuthService:
    def __init__(
        self,
        db: Session,
        *,
        settings: Settings,
        transport: FacebookOAuthTransport | None = None,
    ):
        self.db = db
        self.settings = settings
        self.credential_store = PlatformCredentialStore(db, settings=settings)
        self.transport_override = transport

    def configuration(self, *, workspace_id: UUID | None = None) -> dict:
        runtime, source, stored = self._runtime_configuration(workspace_id)
        envelope = self._envelope()
        missing: list[str] = []
        requested_scopes = set(self._requested_scopes(runtime))
        if not str(runtime.facebook_app_id or "").strip():
            missing.append("FACEBOOK_APP_ID")
        if not str(runtime.facebook_app_secret or "").strip():
            missing.append("FACEBOOK_APP_SECRET")
        if not str(runtime.facebook_oauth_redirect_uri or "").strip():
            missing.append("FACEBOOK_OAUTH_REDIRECT_URI")
        if not re.fullmatch(r"v\d+\.\d+", str(runtime.facebook_graph_api_version or "")):
            missing.append("FACEBOOK_GRAPH_API_VERSION")
        if not envelope.configured:
            missing.append("PLATFORM_CREDENTIAL_ENCRYPTION_KEY_REF")
        if (
            not FACEBOOK_REQUIRED_PUBLISH_SCOPES.issubset(requested_scopes)
            or not requested_scopes.issubset(FACEBOOK_OAUTH_SCOPE_ALLOWLIST)
        ):
            missing.append("FACEBOOK_OAUTH_SCOPES")
        return {
            "configured": not missing,
            "missing_configuration": missing,
            "graph_api_version": runtime.facebook_graph_api_version,
            "redirect_uri": runtime.facebook_oauth_redirect_uri,
            "requested_scopes": self._requested_scopes(runtime),
            "encrypted_credential_store_ready": envelope.configured,
            "raw_token_entry_required": False,
            "source": source,
            "app_id": str(runtime.facebook_app_id or "").strip() or None,
            "app_secret_configured": bool(str(runtime.facebook_app_secret or "").strip()),
            "editable": True,
            "updated_at": stored.updated_at if stored is not None else None,
        }

    def save_configuration(
        self,
        *,
        workspace_id: UUID,
        subject: str,
        app_id: str,
        app_secret: str | None,
        redirect_uri: str,
        graph_api_version: str,
        requested_scopes: list[str],
    ) -> dict:
        scopes = sorted({item.strip() for item in requested_scopes if item.strip()})
        if (
            not FACEBOOK_REQUIRED_PUBLISH_SCOPES.issubset(scopes)
            or not set(scopes).issubset(FACEBOOK_OAUTH_SCOPE_ALLOWLIST)
        ):
            raise FacebookOAuthError(
                "facebook_oauth_scopes_invalid",
                "Meta OAuth scopes must use the approved Page allowlist and include pages_show_list and pages_manage_posts",
            )
        try:
            key_ref = resolve_platform_credential_key_ref(
                self.settings,
                create_local=True,
            )
        except PlatformCredentialKeyStoreError as exc:
            raise FacebookOAuthError(
                "facebook_credential_key_unavailable",
                "The server could not initialize its local credential key store",
                http_status=503,
            ) from exc
        envelope = PlatformSecretEnvelope(key_ref=key_ref)
        if not envelope.configured:
            raise FacebookOAuthError(
                "facebook_credential_key_unavailable",
                "A managed platform credential encryption key is required",
                http_status=503,
            )

        stored = self._stored_configuration(workspace_id)
        if stored is None:
            if not app_secret:
                raise FacebookOAuthError(
                    "facebook_app_secret_required",
                    "App Secret is required when creating Meta OAuth configuration",
                )
            stored = PlatformIntegrationConfiguration(
                id=uuid4(),
                workspace_id=workspace_id,
                provider=FACEBOOK_PROVIDER,
                app_id=app_id,
                encrypted_app_secret="pending",
                oauth_redirect_uri=redirect_uri,
                graph_api_version=graph_api_version,
                requested_scopes_json=scopes,
                configured_by_subject=subject,
                key_version="envelope-v1",
                enabled=True,
            )
            self.db.add(stored)

        stored.app_id = app_id
        stored.oauth_redirect_uri = redirect_uri
        stored.graph_api_version = graph_api_version
        stored.requested_scopes_json = scopes
        stored.configured_by_subject = subject
        stored.enabled = True
        if app_secret:
            stored.encrypted_app_secret = envelope.encrypt(
                app_secret,
                context=self._app_secret_context(workspace_id),
            )
        try:
            self.db.commit()
            self.db.refresh(stored)
        except IntegrityError as exc:
            self.db.rollback()
            raise FacebookOAuthError(
                "facebook_oauth_configuration_conflict",
                "Meta OAuth configuration could not be saved",
                http_status=409,
            ) from exc
        return self.configuration(workspace_id=workspace_id)

    def start(self, *, workspace_id: UUID, subject: str) -> dict:
        runtime, source, _stored = self._runtime_configuration(workspace_id)
        config = self.configuration(workspace_id=workspace_id)
        if not config["configured"]:
            raise FacebookOAuthError(
                "facebook_oauth_not_configured",
                "Meta OAuth is not configured on the API server",
                http_status=503,
            )
        state = secrets.token_urlsafe(40)
        now = datetime.now(UTC)
        session = PlatformOAuthSession(
            id=uuid4(),
            workspace_id=workspace_id,
            provider=FACEBOOK_PROVIDER,
            created_by_subject=subject,
            state_hash=self._hash_state(state),
            status=FACEBOOK_OAUTH_PENDING,
            redirect_uri=runtime.facebook_oauth_redirect_uri,
            requested_scopes_json=self._requested_scopes(runtime),
            granted_scopes_json=[],
            expires_at=now + timedelta(minutes=max(1, int(self.settings.facebook_oauth_session_ttl_minutes))),
            metadata_json={
                "token_value_exposed": False,
                "configuration_source": source,
                "graph_api_version": runtime.facebook_graph_api_version,
                "app_id": runtime.facebook_app_id,
            },
        )
        self.db.add(session)
        self.db.commit()
        self.db.refresh(session)
        authorization_url = "https://www.facebook.com/{version}/dialog/oauth?{query}".format(
            version=runtime.facebook_graph_api_version,
            query=urlencode(
                {
                    "client_id": runtime.facebook_app_id,
                    "redirect_uri": runtime.facebook_oauth_redirect_uri,
                    "state": state,
                    "scope": ",".join(self._requested_scopes(runtime)),
                    "response_type": "code",
                }
            ),
        )
        return {
            "connection_id": session.id,
            "authorization_url": authorization_url,
            "expires_at": session.expires_at,
            "token_value_exposed": False,
        }

    def complete_callback(
        self,
        *,
        workspace_id: UUID,
        subject: str,
        state: str,
        code: str,
    ) -> dict:
        session = self.db.scalar(
            select(PlatformOAuthSession).where(
                PlatformOAuthSession.state_hash == self._hash_state(state),
                PlatformOAuthSession.workspace_id == workspace_id,
                PlatformOAuthSession.created_by_subject == subject,
                PlatformOAuthSession.provider == FACEBOOK_PROVIDER,
            )
        )
        if (
            session is None
            or session.workspace_id != workspace_id
            or session.created_by_subject != subject
            or session.provider != FACEBOOK_PROVIDER
        ):
            raise FacebookOAuthError("facebook_oauth_state_invalid", "Facebook OAuth state is invalid or belongs to another session")
        self._assert_pending(session)
        runtime, _source, _stored = self._runtime_configuration(workspace_id)
        config = self.configuration(workspace_id=workspace_id)
        if not config["configured"]:
            raise FacebookOAuthError(
                "facebook_oauth_not_configured",
                "Meta OAuth configuration is no longer available on the API server",
                http_status=503,
            )
        transport = self.transport_override or RequestsFacebookOAuthTransport(
            runtime.model_copy(update={"facebook_oauth_redirect_uri": session.redirect_uri})
        )
        try:
            short_token = transport.exchange_code(code)
            user_token = transport.exchange_long_lived_user_token(short_token)
            granted_scopes = transport.fetch_granted_scopes(user_token)
            raw_pages = transport.fetch_pages(user_token)
            pages: list[dict] = []
            seen_page_ids: set[str] = set()
            for row in raw_pages:
                page_id = str(row.get("id") or "").strip()
                name = str(row.get("name") or "").strip()
                page_token = str(row.get("access_token") or "").strip()
                if not page_id or not name or not page_token or page_id in seen_page_ids:
                    continue
                seen_page_ids.add(page_id)
                tasks = sorted({str(item) for item in (row.get("tasks") or []) if str(item).strip()})
                picture = row.get("picture") if isinstance(row.get("picture"), dict) else {}
                picture_data = picture.get("data") if isinstance(picture.get("data"), dict) else {}
                picture_url = str(picture_data.get("url") or "").strip() or None
                pages.append(
                    {
                        "page_id": page_id,
                        "display_name": name,
                        "tasks": tasks,
                        "picture_url": picture_url,
                        "access_token": page_token,
                    }
                )
            if not pages:
                raise FacebookOAuthError("facebook_oauth_no_pages", "No manageable Facebook Page with a Page token was returned")

            payload = json.dumps(
                {"pages": pages, "granted_scopes": sorted(granted_scopes)},
                separators=(",", ":"),
            )
            session.encrypted_payload = self._envelope().encrypt(
                payload,
                context=self._session_context(session),
            )
            session.granted_scopes_json = sorted(granted_scopes)
            session.status = FACEBOOK_OAUTH_PAGE_SELECTION
            session.error_code = None
            session.error_message = None
            self.db.commit()
        except FacebookOAuthError as exc:
            session.status = FACEBOOK_OAUTH_FAILED
            session.error_code = exc.code
            session.error_message = exc.message
            session.encrypted_payload = None
            self.db.commit()
            raise
        return self._safe_session(session)

    def get_session(self, connection_id: UUID, *, workspace_id: UUID, subject: str) -> dict:
        session = self._get_owned_session(connection_id, workspace_id=workspace_id, subject=subject)
        self._expire_if_needed(session)
        return self._safe_session(session)

    def connect_page(
        self,
        connection_id: UUID,
        *,
        workspace_id: UUID,
        subject: str,
        page_id: str,
        priority: int,
    ) -> dict:
        session = self._get_owned_session(connection_id, workspace_id=workspace_id, subject=subject)
        self._expire_if_needed(session)
        if session.status != FACEBOOK_OAUTH_PAGE_SELECTION:
            raise FacebookOAuthError("facebook_oauth_page_not_ready", "Facebook OAuth session is not ready for Page selection")
        payload = self._decrypt_session_payload(session)
        page = next((item for item in payload["pages"] if item["page_id"] == page_id), None)
        if page is None:
            raise FacebookOAuthError("facebook_oauth_page_invalid", "Selected Facebook Page does not belong to this OAuth session")

        now = datetime.now(UTC)
        runtime, _source, _stored = self._runtime_configuration(workspace_id)
        granted_scopes = set(payload["granted_scopes"])
        page_tasks = {
            str(value).strip().upper()
            for value in page["tasks"]
            if str(value).strip()
        }
        publish_scopes = sorted(
            granted_scopes.intersection(FACEBOOK_REQUIRED_PUBLISH_SCOPES)
        )
        publish_capability_ready = (
            FACEBOOK_REQUIRED_PUBLISH_SCOPES.issubset(granted_scopes)
            and FACEBOOK_REQUIRED_PUBLISH_TASK in page_tasks
        )
        existing = self.db.scalar(
            select(PlatformAccount).where(
                PlatformAccount.workspace_id == workspace_id,
                PlatformAccount.platform == PublishTargetPlatform.FACEBOOK_REELS,
                PlatformAccount.external_account_id == page_id,
            )
        )
        created = existing is None
        account = existing or PlatformAccount(
            id=uuid4(),
            workspace_id=workspace_id,
            platform=PublishTargetPlatform.FACEBOOK_REELS,
            display_name=page["display_name"],
            external_account_id=page_id,
            status=PlatformAccountStatus.ACTIVE,
            priority=priority,
            is_on_hold=False,
        )
        if created:
            self.db.add(account)

        insights_scopes = sorted(granted_scopes.intersection({"read_insights", "pages_read_engagement"}))
        insights_ready = {"read_insights", "pages_read_engagement"}.issubset(granted_scopes)
        account.display_name = page["display_name"]
        if created:
            account.priority = priority
        if not publish_capability_ready:
            account.status = PlatformAccountStatus.PAUSED
            account.is_on_hold = True
            account.hold_reason = (
                f"{FACEBOOK_OAUTH_CAPABILITY_HOLD_PREFIX} reconnect the Page and grant "
                "pages_manage_posts with the CREATE_CONTENT Page task"
            )
        elif created or any(
            str(account.hold_reason or "").startswith(prefix)
            for prefix in (
                FACEBOOK_OAUTH_CAPABILITY_HOLD_PREFIX,
                FACEBOOK_SAFETY_HOLD_PREFIX,
            )
        ):
            account.status = PlatformAccountStatus.ACTIVE
            account.is_on_hold = False
            account.hold_reason = None
        account.metadata_json = {
            **(account.metadata_json or {}),
            "graph_api_version": runtime.facebook_graph_api_version,
            "metrics_insights_enabled": insights_ready,
            "facebook_insights_token_type": "PAGE_ACCESS_TOKEN",
            "facebook_insights_verified_external_account_id": page_id if insights_ready else None,
            "facebook_verified_insights_scopes": insights_scopes,
            "facebook_insights_scopes_verified_at": now.isoformat() if insights_ready else None,
            "facebook_insights_object_id_source": "external_reel_id",
            "facebook_publish_capability_verified": publish_capability_ready,
            "facebook_verified_publish_scopes": publish_scopes,
            "facebook_publish_capability_verified_at": (
                now.isoformat() if publish_capability_ready else None
            ),
            "facebook_oauth_connection_id": str(session.id),
            "facebook_oauth_connected_at": now.isoformat(),
            "facebook_oauth_requested_scopes": list(
                session.requested_scopes_json or self._requested_scopes(runtime)
            ),
            "facebook_page_tasks": page["tasks"],
            "facebook_page_picture_url": page.get("picture_url"),
            "credential_source": "META_OAUTH",
        }
        self.credential_store.store_facebook_page_token(
            account,
            page["access_token"],
            metadata={"oauth_connection_id": str(session.id), "page_id": page_id},
        )
        remaining_pages = [item for item in payload["pages"] if item["page_id"] != page_id]
        remaining_publishable_pages = [
            item
            for item in remaining_pages
            if FACEBOOK_REQUIRED_PUBLISH_SCOPES.issubset(granted_scopes)
            and FACEBOOK_REQUIRED_PUBLISH_TASK
            in {str(task).strip().upper() for task in item.get("tasks", [])}
        ]
        previous_page_ids = [
            str(value)
            for value in (session.metadata_json or {}).get("connected_page_ids", [])
            if str(value).strip()
        ]
        previous_account_ids = [
            str(value)
            for value in (session.metadata_json or {}).get("platform_account_ids", [])
            if str(value).strip()
        ]
        session.metadata_json = {
            **(session.metadata_json or {}),
            "selected_page_id": page_id,
            "platform_account_id": str(account.id),
            "connected_page_ids": list(dict.fromkeys([*previous_page_ids, page_id])),
            "platform_account_ids": list(dict.fromkeys([*previous_account_ids, str(account.id)])),
            "token_value_exposed": False,
        }
        if remaining_publishable_pages:
            # Retain only tokens that can still be selected. Non-publishable
            # Page tokens are discarded after the operator makes a selection.
            payload["pages"] = remaining_publishable_pages
            session.encrypted_payload = self._envelope().encrypt(
                json.dumps(payload, separators=(",", ":")),
                context=self._session_context(session),
            )
            session.status = FACEBOOK_OAUTH_PAGE_SELECTION
            session.completed_at = None
        else:
            session.status = FACEBOOK_OAUTH_COMPLETED
            session.completed_at = now
            session.encrypted_payload = None
        try:
            self.db.flush()
            setup_check = PlatformAccountService(
                self.db,
                settings=self.settings,
            ).facebook_setup_check(account.id)
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise FacebookOAuthError("facebook_page_already_connected", "Facebook Page is already connected in this workspace", http_status=409) from exc
        self.db.refresh(account)
        return {
            "account": account,
            "setup_check": setup_check,
            "created": created,
            "token_value_exposed": False,
        }

    def _safe_session(self, session: PlatformOAuthSession) -> dict:
        pages: list[dict] = []
        if session.status == FACEBOOK_OAUTH_PAGE_SELECTION and session.encrypted_payload:
            payload = self._decrypt_session_payload(session)
            pages = [
                {
                    "page_id": item["page_id"],
                    "display_name": item["display_name"],
                    "tasks": item["tasks"],
                    "picture_url": item.get("picture_url"),
                }
                for item in payload["pages"]
            ]
        return {
            "connection_id": session.id,
            "status": session.status,
            "pages": pages,
            "granted_scopes": list(session.granted_scopes_json or []),
            "expires_at": session.expires_at,
            "error_code": session.error_code,
            "error_message": session.error_message,
            "token_value_exposed": False,
        }

    def _decrypt_session_payload(self, session: PlatformOAuthSession) -> dict:
        plaintext = self._envelope().decrypt(
            session.encrypted_payload,
            context=self._session_context(session),
        )
        if not plaintext:
            raise FacebookOAuthError("facebook_oauth_payload_unavailable", "Encrypted Facebook OAuth payload could not be resolved")
        try:
            payload = json.loads(plaintext)
        except json.JSONDecodeError as exc:
            raise FacebookOAuthError("facebook_oauth_payload_invalid", "Encrypted Facebook OAuth payload is invalid") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list) or not isinstance(payload.get("granted_scopes"), list):
            raise FacebookOAuthError("facebook_oauth_payload_invalid", "Encrypted Facebook OAuth payload is invalid")
        return payload

    def _get_owned_session(self, connection_id: UUID, *, workspace_id: UUID, subject: str) -> PlatformOAuthSession:
        session = self.db.get(PlatformOAuthSession, connection_id)
        if (
            session is None
            or session.workspace_id != workspace_id
            or session.created_by_subject != subject
            or session.provider != FACEBOOK_PROVIDER
        ):
            raise FacebookOAuthError("facebook_oauth_session_not_found", "Facebook OAuth session was not found", http_status=404)
        return session

    def _assert_pending(self, session: PlatformOAuthSession) -> None:
        self._expire_if_needed(session)
        if session.status != FACEBOOK_OAUTH_PENDING:
            raise FacebookOAuthError("facebook_oauth_state_replayed", "Facebook OAuth state was already used or is no longer pending", http_status=409)

    def _expire_if_needed(self, session: PlatformOAuthSession) -> None:
        expires_at = session.expires_at
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC) and session.status not in {FACEBOOK_OAUTH_COMPLETED, FACEBOOK_OAUTH_FAILED, FACEBOOK_OAUTH_EXPIRED}:
            session.status = FACEBOOK_OAUTH_EXPIRED
            session.encrypted_payload = None
            self.db.commit()
        if session.status == FACEBOOK_OAUTH_EXPIRED:
            raise FacebookOAuthError("facebook_oauth_session_expired", "Facebook OAuth session expired", http_status=410)

    def _requested_scopes(self, settings: Settings | None = None) -> list[str]:
        settings = settings or self.settings
        return sorted({
            item.strip()
            for item in str(settings.facebook_oauth_scopes or "").split(",")
            if item.strip()
        })

    def _envelope(self) -> PlatformSecretEnvelope:
        return PlatformSecretEnvelope(
            key_ref=resolve_platform_credential_key_ref(self.settings),
        )

    def _stored_configuration(self, workspace_id: UUID) -> PlatformIntegrationConfiguration | None:
        return self.db.scalar(
            select(PlatformIntegrationConfiguration).where(
                PlatformIntegrationConfiguration.workspace_id == workspace_id,
                PlatformIntegrationConfiguration.provider == FACEBOOK_PROVIDER,
                PlatformIntegrationConfiguration.enabled.is_(True),
            )
        )

    def _runtime_configuration(
        self,
        workspace_id: UUID | None,
    ) -> tuple[Settings, str, PlatformIntegrationConfiguration | None]:
        if workspace_id is None:
            source = "ENVIRONMENT" if self.settings.facebook_app_id or self.settings.facebook_app_secret else "NONE"
            return self.settings, source, None
        stored = self._stored_configuration(workspace_id)
        if stored is None:
            source = "ENVIRONMENT" if self.settings.facebook_app_id or self.settings.facebook_app_secret else "NONE"
            return self.settings, source, None
        secret = self._envelope().decrypt(
            stored.encrypted_app_secret,
            context=self._app_secret_context(workspace_id),
        )
        runtime = self.settings.model_copy(
            update={
                "facebook_app_id": stored.app_id,
                "facebook_app_secret": secret,
                "facebook_oauth_redirect_uri": stored.oauth_redirect_uri,
                "facebook_graph_api_version": stored.graph_api_version,
                "facebook_oauth_scopes": ",".join(
                    str(item).strip()
                    for item in (stored.requested_scopes_json or [])
                    if str(item).strip()
                ),
            }
        )
        return runtime, "DATABASE", stored

    @staticmethod
    def _app_secret_context(workspace_id: UUID) -> str:
        return f"facebook-app-secret:{workspace_id}:{FACEBOOK_PROVIDER}"

    @staticmethod
    def _hash_state(state: str) -> str:
        return hashlib.sha256(state.encode("utf-8")).hexdigest()

    @staticmethod
    def _session_context(session: PlatformOAuthSession) -> str:
        return f"facebook-oauth-session:{session.id}:{session.workspace_id}"
