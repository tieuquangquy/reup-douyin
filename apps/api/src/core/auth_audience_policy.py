"""Surface authorization: Operator Studio vs Ops Console vs API UI tooling."""

from __future__ import annotations

from typing import Protocol

from fastapi import HTTPException, Request, status

from src.core.settings import Settings

AUTH_CLIENT_OPERATOR = "operator"
AUTH_CLIENT_OPS = "ops"
AUTH_CLIENT_API_UI = "api-ui"
# Backward-compatible alias used by older web clients.
AUTH_CLIENT_WEB_ALIAS = "web"

_OPS_ADMIN_ROLES = frozenset({"owner", "admin"})
_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

_API_UI_MUTATION_ALLOWLIST = frozenset(
    {
        ("POST", "/auth/refresh"),
        ("POST", "/auth/logout"),
        ("POST", "/auth/invites/accept"),
    }
)


class _PrincipalLike(Protocol):
    azp: str | None
    audience: str | None
    scopes: tuple[str, ...]
    roles: tuple[str, ...]


def normalize_auth_client(value: str | None) -> str:
    normalized = (value or AUTH_CLIENT_OPERATOR).strip().lower().replace("_", "-")
    if normalized in {"api", "api-ui", "swagger"}:
        return AUTH_CLIENT_API_UI
    if normalized in {"ops", "ops-console", "backend"}:
        return AUTH_CLIENT_OPS
    if normalized in {"web", "operator", "frontend", "studio"}:
        return AUTH_CLIENT_OPERATOR
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail="client must be 'operator', 'ops', or 'api-ui'",
    )


def audience_for_client(settings: Settings, client: str) -> str:
    if client == AUTH_CLIENT_API_UI:
        return settings.effective_api_audience
    if client == AUTH_CLIENT_OPS:
        return settings.effective_ops_audience
    return settings.effective_web_audience


def scopes_for_client(client: str) -> list[str]:
    if client == AUTH_CLIENT_API_UI:
        return ["api:inspect"]
    if client == AUTH_CLIENT_OPS:
        return ["ops"]
    return ["operator"]


def role_may_use_ops_console(roles: list[str] | tuple[str, ...]) -> bool:
    return any(role in _OPS_ADMIN_ROLES for role in roles)


def is_api_ui_principal(principal: _PrincipalLike, settings: Settings) -> bool:
    if principal.azp == AUTH_CLIENT_API_UI:
        return True
    if principal.audience == settings.effective_api_audience:
        return True
    return "api:inspect" in principal.scopes


def is_ops_principal(principal: _PrincipalLike, settings: Settings) -> bool:
    if principal.azp == AUTH_CLIENT_OPS:
        return True
    if principal.audience == settings.effective_ops_audience:
        return True
    return "ops" in principal.scopes


def is_operator_principal(principal: _PrincipalLike, settings: Settings) -> bool:
    if principal.azp in {AUTH_CLIENT_OPERATOR, AUTH_CLIENT_WEB_ALIAS}:
        return True
    if principal.audience == settings.effective_web_audience and not is_ops_principal(principal, settings):
        if is_api_ui_principal(principal, settings):
            return False
        return True
    return "operator" in principal.scopes


def assert_client_may_access_request(
    *,
    request: Request,
    principal: _PrincipalLike | None,
    settings: Settings,
) -> None:
    """Fail closed by surface: api-ui read-only; /ops/* requires ops; operator cannot hit /ops/*."""

    if principal is None:
        return

    method = request.method.upper()
    path = request.url.path.rstrip("/") or "/"

    if is_api_ui_principal(principal, settings):
        if method in _SAFE_METHODS:
            return
        if (method, path) in _API_UI_MUTATION_ALLOWLIST:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "API UI token is read-only on product routes. "
                "Use Operator Studio or Ops Console login for writes."
            ),
        )

    is_ops_api = path == "/ops" or path.startswith("/ops/")
    if is_ops_api:
        if is_ops_principal(principal, settings):
            if not role_may_use_ops_console(principal.roles):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Ops Console requires owner or admin role",
                )
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Ops API requires an Ops Console (ops) token. Sign in at /auth/ops/login.",
        )

    # Non-/ops product APIs: operator or ops (Ops Console pages call shared jobs/publish APIs).
    if is_operator_principal(principal, settings) or is_ops_principal(principal, settings):
        if is_ops_principal(principal, settings) and not role_may_use_ops_console(principal.roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ops Console requires owner or admin role",
            )
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Bearer token surface is not allowed for this route",
    )
