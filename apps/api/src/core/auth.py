from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import base64
import hashlib
import hmac
import json
from typing import Any
from uuid import UUID

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.core.auth_audience_policy import assert_client_may_access_request
from src.core.settings import Settings, get_settings


security = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    """Authenticated SaaS principal derived from a signed bearer token.

    Phase 1 uses an internal HS256 JWT verifier implemented with the Python
    standard library to avoid introducing a dependency before the identity
    provider is finalized. This module is intentionally isolated so it can be
    replaced by a managed IdP/JWKS verifier without touching route handlers.
    """

    subject: str
    workspace_id: UUID
    roles: tuple[str, ...]
    token_id: str | None = None
    audience: str | None = None
    azp: str | None = None
    scopes: tuple[str, ...] = ()


def _decode_base64url(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _encode_base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _verify_hs256_jwt(
    token: str,
    secret: str,
    *,
    issuer: str | None = None,
    accepted_audiences: frozenset[str] | None = None,
) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token")

    header_segment, payload_segment, signature_segment = parts
    try:
        header = json.loads(_decode_base64url(header_segment))
        payload = json.loads(_decode_base64url(payload_segment))
        signature = _decode_base64url(signature_segment)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token") from exc

    if header.get("alg") != "HS256" or header.get("typ") not in {None, "JWT"}:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unsupported bearer token")

    signed = f"{header_segment}.{payload_segment}".encode("ascii")
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token signature")

    expires_at = payload.get("exp")
    if expires_at is not None:
        try:
            if datetime.now(UTC).timestamp() >= float(expires_at):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token expired")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token expiry") from exc

    not_before = payload.get("nbf")
    if not_before is not None:
        try:
            if datetime.now(UTC).timestamp() < float(not_before):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token not active")
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid bearer token activation time") from exc

    if issuer:
        if payload.get("iss") != issuer:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token issuer mismatch")

    if accepted_audiences:
        aud = payload.get("aud")
        if isinstance(aud, list):
            if not any(isinstance(item, str) and item in accepted_audiences for item in aud):
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token audience mismatch")
        elif not isinstance(aud, str) or aud not in accepted_audiences:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token audience mismatch")

    return payload


def create_internal_hs256_token(
    *,
    subject: str,
    workspace_id: UUID,
    secret: str,
    roles: list[str] | None = None,
    expires_at: int | None = None,
    issuer: str | None = None,
    audience: str | None = None,
    token_id: str | None = None,
    azp: str | None = None,
    scopes: list[str] | None = None,
) -> str:
    """Create an HS256 JWT for local operator sessions and tests.

    Application login/register issue tokens through this helper. Production SaaS
    may later replace issuance with an IdP while keeping the same bearer shape.
    """

    header = {"alg": "HS256", "typ": "JWT"}
    payload: dict[str, Any] = {"sub": subject, "workspace_id": str(workspace_id), "roles": roles or ["operator"]}
    if expires_at is not None:
        payload["exp"] = expires_at
    if issuer:
        payload["iss"] = issuer
    if audience:
        payload["aud"] = audience
    if token_id:
        payload["jti"] = token_id
    if azp:
        payload["azp"] = azp
    if scopes:
        payload["scope"] = " ".join(scopes)
        payload["scopes"] = scopes
    header_segment = _encode_base64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_segment = _encode_base64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signed = f"{header_segment}.{payload_segment}".encode("ascii")
    signature = _encode_base64url(hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).digest())
    return f"{header_segment}.{payload_segment}.{signature}"


def get_current_principal(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedPrincipal | None:
    """Resolve the authenticated principal for the current request.

    When `API_AUTH_REQUIRED=false`, this returns `None` for local-only legacy
    workflows. Production validation forbids disabling auth.
    """

    if not settings.api_auth_required:
        request.state.principal = None
        request.state.workspace_id = None
        return None

    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")

    payload = _verify_hs256_jwt(
        credentials.credentials,
        settings.jwt_secret_key,
        issuer=settings.jwt_issuer,
        accepted_audiences=settings.accepted_jwt_audiences,
    )
    subject = payload.get("sub")
    workspace_claim = payload.get("workspace_id") or payload.get("wid")
    if not isinstance(subject, str) or not subject.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token missing subject")
    if not isinstance(workspace_claim, str) or not workspace_claim.strip():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token missing workspace_id")

    try:
        workspace_id = UUID(workspace_claim)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token has invalid workspace_id") from exc

    raw_roles = payload.get("roles", [])
    roles = tuple(role for role in raw_roles if isinstance(role, str)) if isinstance(raw_roles, list) else ()
    jti = payload.get("jti")
    token_id = jti if isinstance(jti, str) else None
    aud_raw = payload.get("aud")
    audience = aud_raw if isinstance(aud_raw, str) else (aud_raw[0] if isinstance(aud_raw, list) and aud_raw else None)
    azp_raw = payload.get("azp")
    azp = azp_raw if isinstance(azp_raw, str) else None
    scopes_raw = payload.get("scopes")
    if isinstance(scopes_raw, list):
        scopes = tuple(item for item in scopes_raw if isinstance(item, str))
    else:
        scope_str = payload.get("scope")
        scopes = tuple(part for part in str(scope_str).split() if part) if isinstance(scope_str, str) else ()
    principal = AuthenticatedPrincipal(
        subject=subject,
        workspace_id=workspace_id,
        roles=roles,
        token_id=token_id,
        audience=audience if isinstance(audience, str) else None,
        azp=azp,
        scopes=scopes,
    )
    assert_client_may_access_request(request=request, principal=principal, settings=settings)
    request.state.principal = principal
    request.state.workspace_id = workspace_id
    return principal


def get_current_workspace(principal: AuthenticatedPrincipal | None = Depends(get_current_principal)) -> UUID | None:
    """Return the tenant workspace from the authenticated principal.

    New route/service code must use this dependency instead of accepting
    arbitrary `workspace_id` query/body values. Legacy routes remain protected
    globally and should be migrated incrementally to this dependency.
    """

    if principal is None:
        return None
    return principal.workspace_id
