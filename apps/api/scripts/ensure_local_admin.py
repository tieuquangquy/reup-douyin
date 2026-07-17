"""Ensure a local owner/admin operator exists for Phase 1 development.

Usage (from apps/api):
  python -m scripts.ensure_local_admin

Env overrides:
  LOCAL_ADMIN_EMAIL (default admin@local.test)
  LOCAL_ADMIN_PASSWORD (default LocalAdmin!23456)
  LOCAL_ADMIN_WORKSPACE_SLUG (default local)
"""

from __future__ import annotations

import os
import sys

# Allow `python -m scripts.ensure_local_admin` from apps/api
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.db.bootstrap import ensure_default_workspace
from src.db.session import get_engine
from src.models.auth_session import WorkspaceMembership
from src.models.foundation import Workspace
from src.models.operators import Operator
from src.services.password_hashing import hash_password
import src.models  # noqa: F401


DEFAULT_EMAIL = "admin@local.test"
DEFAULT_PASSWORD = "LocalAdmin!23456"
DEFAULT_SLUG = "local"


def ensure_local_admin(
    *,
    email: str = DEFAULT_EMAIL,
    password: str = DEFAULT_PASSWORD,
    workspace_slug: str = DEFAULT_SLUG,
) -> tuple[Operator, WorkspaceMembership, bool]:
    """Create or upgrade local admin. Returns (operator, membership, created)."""

    get_settings.cache_clear()
    engine = get_engine()
    normalized_email = email.strip().lower()
    created = False

    with Session(engine) as db:
        workspace = ensure_default_workspace(db) if workspace_slug in {"local", "local-workspace"} else None
        if workspace is None:
            workspace = db.scalar(select(Workspace).where(Workspace.slug == workspace_slug.strip().lower()))
            if workspace is None:
                workspace = Workspace(
                    name=workspace_slug.replace("-", " ").title(),
                    slug=workspace_slug.strip().lower(),
                    description="Workspace for local admin bootstrap",
                )
                db.add(workspace)
                db.flush()

        operator = db.scalar(select(Operator).where(Operator.email == normalized_email))
        if operator is None:
            operator = Operator(
                workspace_id=workspace.id,
                email=normalized_email,
                password_hash=hash_password(password),
                display_name="Local Admin",
                is_active=True,
                roles_csv="owner",
            )
            db.add(operator)
            db.flush()
            created = True
        else:
            operator.password_hash = hash_password(password)
            operator.is_active = True
            operator.roles_csv = "owner"
            if not operator.display_name:
                operator.display_name = "Local Admin"

        membership = db.scalar(
            select(WorkspaceMembership).where(
                WorkspaceMembership.operator_id == operator.id,
                WorkspaceMembership.workspace_id == workspace.id,
            )
        )
        if membership is None:
            membership = WorkspaceMembership(
                operator_id=operator.id,
                workspace_id=workspace.id,
                role="owner",
                is_active=True,
            )
            db.add(membership)
        else:
            membership.role = "owner"
            membership.is_active = True

        db.commit()
        db.refresh(operator)
        db.refresh(membership)
        return operator, membership, created


def main() -> None:
    email = os.environ.get("LOCAL_ADMIN_EMAIL", DEFAULT_EMAIL)
    password = os.environ.get("LOCAL_ADMIN_PASSWORD", DEFAULT_PASSWORD)
    slug = os.environ.get("LOCAL_ADMIN_WORKSPACE_SLUG", DEFAULT_SLUG)
    operator, membership, created = ensure_local_admin(email=email, password=password, workspace_slug=slug)
    action = "created" if created else "updated"
    print(f"local admin {action}")
    print(f"  email:     {operator.email}")
    print(f"  password:  {password}")
    print(f"  role:      {membership.role}")
    print(f"  workspace: {slug}")
    print("  login UI:  http://127.0.0.1:8000/auth/ui")
    print("  studio:    http://localhost:3000/auth/login")


if __name__ == "__main__":
    main()
