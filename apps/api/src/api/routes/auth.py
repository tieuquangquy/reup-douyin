from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.api.auth_ui_html import AUTH_UI_HTML
from src.core.auth import AuthenticatedPrincipal, get_current_principal
from src.core.settings import Settings, get_settings
from src.db.session import get_db_session
from src.services.auth_rate_limit import auth_rate_limiter
from src.services.operator_auth_service import IssuedAuthToken, OperatorAuthService


router = APIRouter(prefix="/auth", tags=["auth"])


class MembershipResponse(BaseModel):
    workspace_id: UUID
    workspace_slug: str
    role: str
    is_active: bool


class AuthTokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_at: int
    refresh_expires_at: int
    workspace_id: UUID
    subject: str
    roles: list[str]
    operator_id: UUID | None = None
    display_name: str | None = None
    client: str = "operator"
    audience: str | None = None
    scopes: list[str] = Field(default_factory=list)


class AuthMeResponse(BaseModel):
    subject: str
    email: str
    workspace_id: UUID
    workspace_slug: str
    roles: list[str]
    operator_id: UUID
    display_name: str | None = None
    memberships: list[MembershipResponse] = Field(default_factory=list)
    client: str | None = None
    audience: str | None = None
    scopes: list[str] = Field(default_factory=list)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8)
    workspace_slug: str = Field(default="local-workspace", min_length=3, max_length=120)
    client: str = Field(default="operator", max_length=32)


class AuthRegisterRequest(AuthLoginRequest):
    display_name: str | None = Field(default=None, max_length=160)


class AuthRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class AuthLogoutRequest(BaseModel):
    refresh_token: str | None = None


class AuthInviteCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = Field(default="operator", max_length=64)
    note: str | None = Field(default=None, max_length=500)


class AuthInviteCreateResponse(BaseModel):
    invite_id: UUID
    email: str
    role: str
    workspace_id: UUID
    expires_at: datetime
    invite_token: str


class AuthInviteAcceptRequest(BaseModel):
    invite_token: str = Field(min_length=16)
    password: str = Field(min_length=8)
    display_name: str | None = Field(default=None, max_length=160)


def get_operator_auth_service(
    db: Session = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> OperatorAuthService:
    return OperatorAuthService(db, settings)


def _configure_rate_limit(settings: Settings) -> None:
    auth_rate_limiter.configure(
        max_attempts=settings.auth_rate_limit_max_attempts,
        window_seconds=settings.auth_rate_limit_window_seconds,
    )


def _to_token_response(issued: IssuedAuthToken) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=issued.access_token,
        refresh_token=issued.refresh_token,
        token_type=issued.token_type,
        expires_at=issued.expires_at,
        refresh_expires_at=issued.refresh_expires_at,
        workspace_id=issued.workspace_id,
        subject=issued.subject,
        roles=issued.roles,
        operator_id=issued.operator_id,
        display_name=issued.display_name,
        client=issued.client,
        audience=issued.audience,
        scopes=issued.scopes,
    )


@router.get("/ui", response_class=HTMLResponse, include_in_schema=False)
def auth_ui() -> HTMLResponse:
    """Backend HTML login for Swagger / API tooling (separate from Next.js Operator login)."""
    return HTMLResponse(content=AUTH_UI_HTML)


@router.post("/login", response_model=AuthTokenResponse)
def login(
    request: AuthLoginRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> AuthTokenResponse:
    _configure_rate_limit(settings)
    auth_rate_limiter.check(request=http_request, action="login", email=request.email)
    issued = service.login(
        email=request.email,
        password=request.password,
        workspace_slug=request.workspace_slug,
        client=request.client,
    )
    return _to_token_response(issued)


@router.post("/register", response_model=AuthTokenResponse)
def register(
    request: AuthRegisterRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> AuthTokenResponse:
    _configure_rate_limit(settings)
    auth_rate_limiter.check(request=http_request, action="register", email=request.email)
    issued = service.register(
        email=request.email,
        password=request.password,
        workspace_slug=request.workspace_slug,
        display_name=request.display_name,
        client=request.client,
    )
    return _to_token_response(issued)


@router.post("/refresh", response_model=AuthTokenResponse)
def refresh(
    request: AuthRefreshRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> AuthTokenResponse:
    _configure_rate_limit(settings)
    auth_rate_limiter.check(request=http_request, action="refresh", email="refresh")
    issued = service.refresh(refresh_token=request.refresh_token)
    return _to_token_response(issued)


@router.post("/logout")
def logout(
    request: AuthLogoutRequest,
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> dict[str, bool]:
    service.logout(refresh_token=request.refresh_token)
    return {"ok": True}


@router.get("/me", response_model=AuthMeResponse)
def me(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> AuthMeResponse:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    view = service.me(principal)
    return AuthMeResponse(
        subject=view.subject,
        email=view.email,
        workspace_id=view.workspace_id,
        workspace_slug=view.workspace_slug,
        roles=view.roles,
        operator_id=view.operator_id,
        display_name=view.display_name,
        memberships=[
            MembershipResponse(
                workspace_id=m.workspace_id,
                workspace_slug=m.workspace_slug,
                role=m.role,
                is_active=m.is_active,
            )
            for m in view.memberships
        ],
        client=view.client,
        audience=view.audience,
        scopes=view.scopes,
    )


@router.post("/invites", response_model=AuthInviteCreateResponse)
def create_invite(
    request: AuthInviteCreateRequest,
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> AuthInviteCreateResponse:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    created = service.create_invite(
        principal=principal,
        email=request.email,
        role=request.role,
        note=request.note,
    )
    return AuthInviteCreateResponse(
        invite_id=created.invite_id,
        email=created.email,
        role=created.role,
        workspace_id=created.workspace_id,
        expires_at=created.expires_at,
        invite_token=created.invite_token,
    )


@router.post("/invites/accept", response_model=AuthTokenResponse)
def accept_invite(
    request: AuthInviteAcceptRequest,
    http_request: Request,
    settings: Settings = Depends(get_settings),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> AuthTokenResponse:
    _configure_rate_limit(settings)
    auth_rate_limiter.check(request=http_request, action="invite_accept", email="invite")
    issued = service.accept_invite(
        invite_token=request.invite_token,
        password=request.password,
        display_name=request.display_name,
    )
    return _to_token_response(issued)


class WorkspaceMemberResponse(BaseModel):
    operator_id: UUID
    email: str
    display_name: str | None = None
    role: str
    is_active: bool
    created_at: datetime | None = None


class WorkspaceMembersResponse(BaseModel):
    members: list[WorkspaceMemberResponse]


class WorkspaceInviteResponse(BaseModel):
    invite_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime | None = None
    note: str | None = None


class WorkspaceInvitesResponse(BaseModel):
    invites: list[WorkspaceInviteResponse]


class WorkspaceMemberUpdateRequest(BaseModel):
    role: str | None = Field(default=None, max_length=64)
    is_active: bool | None = None


@router.get("/workspace/members", response_model=WorkspaceMembersResponse)
def list_workspace_members(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> WorkspaceMembersResponse:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    members = service.list_workspace_members(principal=principal)
    return WorkspaceMembersResponse(
        members=[
            WorkspaceMemberResponse(
                operator_id=m.operator_id,
                email=m.email,
                display_name=m.display_name,
                role=m.role,
                is_active=m.is_active,
                created_at=m.created_at,
            )
            for m in members
        ]
    )


@router.patch("/workspace/members/{operator_id}", response_model=WorkspaceMemberResponse)
def update_workspace_member(
    operator_id: UUID,
    request: WorkspaceMemberUpdateRequest,
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> WorkspaceMemberResponse:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    updated = service.update_workspace_member(
        principal=principal,
        operator_id=operator_id,
        role=request.role,
        is_active=request.is_active,
    )
    return WorkspaceMemberResponse(
        operator_id=updated.operator_id,
        email=updated.email,
        display_name=updated.display_name,
        role=updated.role,
        is_active=updated.is_active,
        created_at=updated.created_at,
    )


@router.get("/workspace/invites", response_model=WorkspaceInvitesResponse)
def list_workspace_invites(
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> WorkspaceInvitesResponse:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    invites = service.list_workspace_invites(principal=principal)
    return WorkspaceInvitesResponse(
        invites=[
            WorkspaceInviteResponse(
                invite_id=i.invite_id,
                email=i.email,
                role=i.role,
                status=i.status,
                expires_at=i.expires_at,
                created_at=i.created_at,
                note=i.note,
            )
            for i in invites
        ]
    )


@router.post("/workspace/invites/{invite_id}/revoke")
def revoke_workspace_invite(
    invite_id: UUID,
    principal: AuthenticatedPrincipal | None = Depends(get_current_principal),
    service: OperatorAuthService = Depends(get_operator_auth_service),
) -> dict[str, bool]:
    if principal is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    return service.revoke_workspace_invite(principal=principal, invite_id=invite_id)
