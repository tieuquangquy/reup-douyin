"""Operator register / login / refresh / invites against durable workspace rows."""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.core.auth import AuthenticatedPrincipal, create_internal_hs256_token
from src.core.auth_audience_policy import (
    AUTH_CLIENT_API_UI,
    AUTH_CLIENT_OPERATOR,
    AUTH_CLIENT_OPS,
    audience_for_client,
    normalize_auth_client,
    role_may_use_ops_console,
    scopes_for_client,
)
from src.core.settings import Settings
from src.db.bootstrap import DEFAULT_WORKSPACE_SLUG, ensure_default_workspace
from src.models.auth_session import OperatorInvite, OperatorRefreshToken, WorkspaceMembership
from src.models.foundation import Workspace
from src.models.operators import Operator
from src.services.password_hashing import hash_password, verify_password

# UI historically used "local-workspace"; DB default slug is "local".
_WORKSPACE_SLUG_ALIASES = {
    "local-workspace": DEFAULT_WORKSPACE_SLUG,
    "local": DEFAULT_WORKSPACE_SLUG,
}
_ADMIN_ROLES = frozenset({"owner", "admin"})


@dataclass(frozen=True)
class IssuedAuthToken:
    access_token: str
    refresh_token: str
    token_type: str
    expires_at: int
    refresh_expires_at: int
    workspace_id: UUID
    subject: str
    roles: list[str]
    operator_id: UUID
    display_name: str | None
    client: str
    audience: str
    scopes: list[str]


@dataclass(frozen=True)
class MembershipView:
    workspace_id: UUID
    workspace_slug: str
    role: str
    is_active: bool


@dataclass(frozen=True)
class AuthMeView:
    subject: str
    workspace_id: UUID
    workspace_slug: str
    roles: list[str]
    operator_id: UUID
    display_name: str | None
    email: str
    memberships: list[MembershipView]
    client: str | None
    audience: str | None
    scopes: list[str]


@dataclass(frozen=True)
class CreatedInvite:
    invite_id: UUID
    email: str
    role: str
    workspace_id: UUID
    expires_at: datetime
    invite_token: str


@dataclass(frozen=True)
class WorkspaceMemberView:
    operator_id: UUID
    email: str
    display_name: str | None
    role: str
    is_active: bool
    created_at: datetime | None


@dataclass(frozen=True)
class WorkspaceInviteView:
    invite_id: UUID
    email: str
    role: str
    status: str
    expires_at: datetime
    created_at: datetime | None
    note: str | None


class OperatorAuthService:
    def __init__(self, db: Session, settings: Settings) -> None:
        self._db = db
        self._settings = settings

    def register(
        self,
        *,
        email: str,
        password: str,
        workspace_slug: str,
        display_name: str | None = None,
        client: str | None = None,
    ) -> IssuedAuthToken:
        if not self._settings.auth_registration_enabled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Public registration is disabled",
            )
        auth_client = normalize_auth_client(client)
        # Public register always binds to Operator Studio.
        if auth_client != AUTH_CLIENT_OPERATOR:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Registration is only available for Operator Studio (client=operator)",
            )
        normalized_email = _normalize_email(email)
        existing = self._db.scalar(select(Operator).where(Operator.email == normalized_email))
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An operator with this email already exists",
            )
        workspace = self._resolve_workspace(workspace_slug)
        role = self._default_role_for_new_member(workspace.id)
        operator = Operator(
            workspace_id=workspace.id,
            email=normalized_email,
            password_hash=hash_password(password),
            display_name=(display_name or "").strip() or None,
            is_active=True,
            roles_csv=role,
        )
        self._db.add(operator)
        self._db.flush()
        self._ensure_membership(operator_id=operator.id, workspace_id=workspace.id, role=role)
        self._db.commit()
        self._db.refresh(operator)
        return self._issue_session(operator, workspace_id=workspace.id, client=AUTH_CLIENT_OPERATOR)

    def login(
        self,
        *,
        email: str,
        password: str,
        workspace_slug: str,
        client: str | None = None,
    ) -> IssuedAuthToken:
        auth_client = normalize_auth_client(client)
        normalized_email = _normalize_email(email)
        operator = self._db.scalar(select(Operator).where(Operator.email == normalized_email))
        if operator is None or not operator.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        if not verify_password(password, operator.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )
        workspace = self._resolve_workspace(workspace_slug)
        membership = self._active_membership(operator.id, workspace.id)
        if membership is None:
            inactive = self._active_membership(operator.id, workspace.id, include_inactive=True)
            if inactive is not None and not inactive.is_active:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )
            # Phase 1: allow home-workspace login without explicit membership row (legacy).
            if operator.workspace_id != workspace.id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid email or password",
                )
            role = (list(operator.roles) or ["operator"])[0]
            membership = self._ensure_membership(
                operator_id=operator.id,
                workspace_id=workspace.id,
                role=role,
            )
            self._db.commit()
        if auth_client == AUTH_CLIENT_OPS and not role_may_use_ops_console([membership.role]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ops Console login requires owner or admin role",
            )
        return self._issue_session(
            operator,
            workspace_id=workspace.id,
            role=membership.role,
            client=auth_client,
        )

    def refresh(self, *, refresh_token: str) -> IssuedAuthToken:
        raw = (refresh_token or "").strip()
        if not raw:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        token_hash = _hash_opaque_token(raw)
        row = self._db.scalar(select(OperatorRefreshToken).where(OperatorRefreshToken.token_hash == token_hash))
        if row is None or row.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
        if _as_utc(row.expires_at) <= datetime.now(UTC):
            row.revoked_at = datetime.now(UTC)
            self._db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")

        operator = self._db.get(Operator, row.operator_id)
        if operator is None or not operator.is_active:
            row.revoked_at = datetime.now(UTC)
            self._db.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        # Rotate: revoke old + issue new pair in one commit.
        membership = self._preferred_membership(operator)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="No active workspace membership")

        auth_client = normalize_auth_client(row.client)
        if auth_client == AUTH_CLIENT_OPS and not role_may_use_ops_console([membership.role]):
            row.revoked_at = datetime.now(UTC)
            self._db.commit()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Ops Console login requires owner or admin role",
            )

        row.revoked_at = datetime.now(UTC)
        issued = self._issue_session(
            operator,
            workspace_id=membership.workspace_id,
            role=membership.role,
            commit=False,
            client=auth_client,
        )
        row.replaced_by_hash = _hash_opaque_token(issued.refresh_token)
        self._db.commit()
        return issued

    def logout(self, *, refresh_token: str | None) -> None:
        raw = (refresh_token or "").strip()
        if not raw:
            return
        token_hash = _hash_opaque_token(raw)
        row = self._db.scalar(select(OperatorRefreshToken).where(OperatorRefreshToken.token_hash == token_hash))
        if row is None or row.revoked_at is not None:
            return
        row.revoked_at = datetime.now(UTC)
        self._db.commit()

    def me(self, principal: AuthenticatedPrincipal) -> AuthMeView:
        operator = self._db.scalar(select(Operator).where(Operator.email == principal.subject.lower()))
        if operator is None or not operator.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Operator not found for this token",
            )
        workspace = self._db.get(Workspace, principal.workspace_id)
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Workspace not found for this token",
            )
        memberships = self._list_memberships(operator.id)
        roles = list(principal.roles) or list(operator.roles) or ["operator"]
        active = next((m for m in memberships if m.workspace_id == principal.workspace_id), None)
        if active is not None:
            roles = [active.role]
        return AuthMeView(
            subject=operator.email,
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            roles=roles,
            operator_id=operator.id,
            display_name=operator.display_name,
            email=operator.email,
            memberships=memberships,
            client=principal.azp,
            audience=principal.audience,
            scopes=list(principal.scopes),
        )

    def create_invite(
        self,
        *,
        principal: AuthenticatedPrincipal,
        email: str,
        role: str = "operator",
        note: str | None = None,
    ) -> CreatedInvite:
        operator = self._require_operator(principal.subject)
        membership = self._active_membership(operator.id, principal.workspace_id)
        if membership is None or membership.role not in _ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required to invite")
        normalized_role = _normalize_role(role)
        if normalized_role == "owner" and membership.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can invite owners")
        normalized_email = _normalize_email(email)
        invite_token = secrets.token_urlsafe(32)
        expires_at = datetime.now(UTC) + timedelta(days=max(1, int(self._settings.auth_invite_ttl_days)))
        invite = OperatorInvite(
            workspace_id=principal.workspace_id,
            email=normalized_email,
            role=normalized_role,
            token_hash=_hash_opaque_token(invite_token),
            invited_by_operator_id=operator.id,
            expires_at=expires_at,
            note=(note or "").strip() or None,
        )
        self._db.add(invite)
        self._db.commit()
        self._db.refresh(invite)
        return CreatedInvite(
            invite_id=invite.id,
            email=invite.email,
            role=invite.role,
            workspace_id=invite.workspace_id,
            expires_at=invite.expires_at,
            invite_token=invite_token,
        )

    def accept_invite(
        self,
        *,
        invite_token: str,
        password: str,
        display_name: str | None = None,
    ) -> IssuedAuthToken:
        raw = (invite_token or "").strip()
        if not raw:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invite_token is required")
        token_hash = _hash_opaque_token(raw)
        invite = self._db.scalar(select(OperatorInvite).where(OperatorInvite.token_hash == token_hash))
        if invite is None or invite.revoked_at is not None or invite.accepted_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or used invite")
        if _as_utc(invite.expires_at) <= datetime.now(UTC):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite expired")

        existing = self._db.scalar(select(Operator).where(Operator.email == invite.email))
        if existing is not None:
            operator = existing
            if not verify_password(password, operator.password_hash):
                # Existing account must prove password ownership when accepting invite.
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Password does not match existing operator",
                )
            if display_name and not operator.display_name:
                operator.display_name = display_name.strip() or None
        else:
            operator = Operator(
                workspace_id=invite.workspace_id,
                email=invite.email,
                password_hash=hash_password(password),
                display_name=(display_name or "").strip() or None,
                is_active=True,
                roles_csv=invite.role,
            )
            self._db.add(operator)
            self._db.flush()

        self._ensure_membership(operator_id=operator.id, workspace_id=invite.workspace_id, role=invite.role)
        invite.accepted_at = datetime.now(UTC)
        self._db.commit()
        self._db.refresh(operator)
        return self._issue_session(
            operator,
            workspace_id=invite.workspace_id,
            role=invite.role,
            client=AUTH_CLIENT_OPERATOR,
        )

    def list_workspace_members(self, *, principal: AuthenticatedPrincipal) -> list[WorkspaceMemberView]:
        self._require_workspace_admin(principal)
        rows = self._db.execute(
            select(WorkspaceMembership, Operator)
            .join(Operator, Operator.id == WorkspaceMembership.operator_id)
            .where(WorkspaceMembership.workspace_id == principal.workspace_id)
            .order_by(WorkspaceMembership.created_at.asc())
        ).all()
        return [
            WorkspaceMemberView(
                operator_id=operator.id,
                email=operator.email,
                display_name=operator.display_name,
                role=membership.role,
                is_active=bool(membership.is_active and operator.is_active),
                created_at=getattr(membership, "created_at", None),
            )
            for membership, operator in rows
        ]

    def list_workspace_invites(self, *, principal: AuthenticatedPrincipal) -> list[WorkspaceInviteView]:
        self._require_workspace_admin(principal)
        now = datetime.now(UTC)
        rows = self._db.scalars(
            select(OperatorInvite)
            .where(
                OperatorInvite.workspace_id == principal.workspace_id,
                OperatorInvite.accepted_at.is_(None),
                OperatorInvite.revoked_at.is_(None),
            )
            .order_by(OperatorInvite.created_at.desc())
        ).all()
        views: list[WorkspaceInviteView] = []
        for invite in rows:
            expired = _as_utc(invite.expires_at) <= now
            views.append(
                WorkspaceInviteView(
                    invite_id=invite.id,
                    email=invite.email,
                    role=invite.role,
                    status="expired" if expired else "pending",
                    expires_at=invite.expires_at,
                    created_at=getattr(invite, "created_at", None),
                    note=invite.note,
                )
            )
        return views

    def revoke_workspace_invite(self, *, principal: AuthenticatedPrincipal, invite_id: UUID) -> dict[str, bool]:
        self._require_workspace_admin(principal)
        invite = self._db.get(OperatorInvite, invite_id)
        if invite is None or invite.workspace_id != principal.workspace_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invite not found")
        if invite.accepted_at is not None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invite already accepted")
        if invite.revoked_at is None:
            invite.revoked_at = datetime.now(UTC)
            self._db.commit()
        return {"ok": True}

    def update_workspace_member(
        self,
        *,
        principal: AuthenticatedPrincipal,
        operator_id: UUID,
        role: str | None = None,
        is_active: bool | None = None,
    ) -> WorkspaceMemberView:
        actor_membership = self._require_workspace_admin(principal)
        if role is None and is_active is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="No updates provided")

        membership = self._active_membership(operator_id, principal.workspace_id, include_inactive=True)
        if membership is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        target = self._db.get(Operator, operator_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

        next_role = _normalize_role(role) if role is not None else membership.role
        next_active = membership.is_active if is_active is None else bool(is_active)

        if membership.role == "owner" and actor_membership.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can manage owners")
        if next_role == "owner" and actor_membership.role != "owner":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only owners can assign owner role")

        demoting_or_disabling_owner = membership.role == "owner" and (next_role != "owner" or not next_active)
        if demoting_or_disabling_owner and self._count_active_owners(principal.workspace_id) <= 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove or demote the last active owner",
            )

        membership.role = next_role
        membership.is_active = next_active
        target.roles_csv = next_role
        if is_active is not None:
            target.is_active = next_active
            if not next_active:
                self._revoke_operator_refresh_tokens(operator_id)

        self._db.commit()
        self._db.refresh(membership)
        self._db.refresh(target)
        return WorkspaceMemberView(
            operator_id=target.id,
            email=target.email,
            display_name=target.display_name,
            role=membership.role,
            is_active=bool(membership.is_active and target.is_active),
            created_at=getattr(membership, "created_at", None),
        )

    def _require_workspace_admin(self, principal: AuthenticatedPrincipal) -> WorkspaceMembership:
        operator = self._require_operator(principal.subject)
        membership = self._active_membership(operator.id, principal.workspace_id)
        if membership is None or membership.role not in _ADMIN_ROLES:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")
        return membership

    def _count_active_owners(self, workspace_id: UUID) -> int:
        return int(
            self._db.scalar(
                select(func.count())
                .select_from(WorkspaceMembership)
                .join(Operator, Operator.id == WorkspaceMembership.operator_id)
                .where(
                    WorkspaceMembership.workspace_id == workspace_id,
                    WorkspaceMembership.role == "owner",
                    WorkspaceMembership.is_active.is_(True),
                    Operator.is_active.is_(True),
                )
            )
            or 0
        )

    def _revoke_operator_refresh_tokens(self, operator_id: UUID) -> None:
        now = datetime.now(UTC)
        rows = self._db.scalars(
            select(OperatorRefreshToken).where(
                OperatorRefreshToken.operator_id == operator_id,
                OperatorRefreshToken.revoked_at.is_(None),
            )
        ).all()
        for row in rows:
            row.revoked_at = now

    def _require_operator(self, subject: str) -> Operator:
        operator = self._db.scalar(select(Operator).where(Operator.email == subject.lower()))
        if operator is None or not operator.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Operator not found for this token")
        return operator

    def _resolve_workspace(self, workspace_slug: str) -> Workspace:
        normalized = _normalize_workspace_slug(workspace_slug)
        target_slug = _WORKSPACE_SLUG_ALIASES.get(normalized, normalized)
        if target_slug == DEFAULT_WORKSPACE_SLUG:
            return ensure_default_workspace(self._db)
        workspace = self._db.scalar(select(Workspace).where(Workspace.slug == target_slug))
        if workspace is not None:
            return workspace
        workspace = Workspace(
            name=target_slug.replace("-", " ").title(),
            slug=target_slug,
            description=f"Workspace created at operator auth for slug={target_slug}",
        )
        self._db.add(workspace)
        self._db.commit()
        self._db.refresh(workspace)
        return workspace

    def _default_role_for_new_member(self, workspace_id: UUID) -> str:
        count = self._db.scalar(
            select(func.count()).select_from(WorkspaceMembership).where(WorkspaceMembership.workspace_id == workspace_id)
        )
        if int(count or 0) == 0:
            return "owner"
        return "operator"

    def _ensure_membership(self, *, operator_id: UUID, workspace_id: UUID, role: str) -> WorkspaceMembership:
        existing = self._active_membership(operator_id, workspace_id, include_inactive=True)
        if existing is not None:
            existing.role = role
            existing.is_active = True
            return existing
        membership = WorkspaceMembership(
            operator_id=operator_id,
            workspace_id=workspace_id,
            role=role,
            is_active=True,
        )
        self._db.add(membership)
        self._db.flush()
        return membership

    def _active_membership(
        self,
        operator_id: UUID,
        workspace_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> WorkspaceMembership | None:
        stmt = select(WorkspaceMembership).where(
            WorkspaceMembership.operator_id == operator_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
        if not include_inactive:
            stmt = stmt.where(WorkspaceMembership.is_active.is_(True))
        return self._db.scalar(stmt)

    def _preferred_membership(self, operator: Operator) -> WorkspaceMembership | None:
        home = self._active_membership(operator.id, operator.workspace_id)
        if home is not None:
            return home
        return self._db.scalar(
            select(WorkspaceMembership)
            .where(WorkspaceMembership.operator_id == operator.id, WorkspaceMembership.is_active.is_(True))
            .order_by(WorkspaceMembership.created_at.asc())
        )

    def _list_memberships(self, operator_id: UUID) -> list[MembershipView]:
        rows = self._db.execute(
            select(WorkspaceMembership, Workspace)
            .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
            .where(WorkspaceMembership.operator_id == operator_id, WorkspaceMembership.is_active.is_(True))
            .order_by(WorkspaceMembership.created_at.asc())
        ).all()
        return [
            MembershipView(
                workspace_id=membership.workspace_id,
                workspace_slug=workspace.slug,
                role=membership.role,
                is_active=membership.is_active,
            )
            for membership, workspace in rows
        ]

    def _issue_session(
        self,
        operator: Operator,
        *,
        workspace_id: UUID,
        role: str | None = None,
        commit: bool = True,
        client: str = AUTH_CLIENT_OPERATOR,
    ) -> IssuedAuthToken:
        auth_client = normalize_auth_client(client)
        resolved_role = role or (list(operator.roles) or ["operator"])[0]
        roles = [resolved_role]
        scopes = scopes_for_client(auth_client)
        audience = audience_for_client(self._settings, auth_client)
        if auth_client == AUTH_CLIENT_API_UI:
            access_ttl = max(1, int(self._settings.auth_api_ui_access_token_ttl_minutes))
        elif auth_client == AUTH_CLIENT_OPS:
            access_ttl = max(1, int(self._settings.auth_ops_access_token_ttl_minutes))
        else:
            access_ttl = max(1, int(self._settings.auth_access_token_ttl_minutes))
        refresh_ttl_days = max(1, int(self._settings.auth_refresh_token_ttl_days))
        now = datetime.now(UTC)
        expires_at = int((now + timedelta(minutes=access_ttl)).timestamp())
        refresh_expires_at_dt = now + timedelta(days=refresh_ttl_days)
        refresh_expires_at = int(refresh_expires_at_dt.timestamp())
        access_token = create_internal_hs256_token(
            subject=operator.email,
            workspace_id=workspace_id,
            secret=self._settings.jwt_secret_key,
            roles=roles,
            expires_at=expires_at,
            issuer=self._settings.jwt_issuer,
            audience=audience,
            token_id=str(uuid4()),
            azp=auth_client,
            scopes=scopes,
        )
        refresh_raw = secrets.token_urlsafe(48)
        self._db.add(
            OperatorRefreshToken(
                operator_id=operator.id,
                token_hash=_hash_opaque_token(refresh_raw),
                expires_at=refresh_expires_at_dt,
                client=auth_client,
            )
        )
        if commit:
            self._db.commit()
        return IssuedAuthToken(
            access_token=access_token,
            refresh_token=refresh_raw,
            token_type="bearer",
            expires_at=expires_at,
            refresh_expires_at=refresh_expires_at,
            workspace_id=workspace_id,
            subject=operator.email,
            roles=roles,
            operator_id=operator.id,
            display_name=operator.display_name,
            client=auth_client,
            audience=audience,
            scopes=scopes,
        )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _hash_opaque_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if len(normalized) < 3:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="email is required")
    return normalized


def _normalize_workspace_slug(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "-")
    if len(normalized) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="workspace_slug is required",
        )
    return normalized


def _normalize_role(value: str) -> str:
    normalized = (value or "operator").strip().lower()
    if normalized not in {"owner", "admin", "operator", "viewer"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported role")
    return normalized


def count_operators(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Operator)) or 0)
