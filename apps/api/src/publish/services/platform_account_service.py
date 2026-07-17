from __future__ import annotations

import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PlatformAccountStatus, PublishTargetPlatform
from src.models.foundation import Workspace
from src.models.publish import PlatformAccount
from src.publish.types import PlatformAccountConfig
from src.schemas.publish import PlatformAccountCreateRequest, PlatformAccountUpdateRequest


class PlatformAccountError(ValueError):
    pass


class PlatformAccountService:
    def __init__(self, db: Session):
        self.db = db

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
            metadata_json=request.metadata_json,
            routing_notes=request.routing_notes,
            notes=request.notes,
        )
        self.db.add(account)
        self.db.commit()
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
            "metadata_json",
            "routing_notes",
            "notes",
        ]:
            if field in provided_fields:
                setattr(account, field, getattr(request, field))
        self.db.commit()
        self.db.refresh(account)
        return account

    def resolve_config(self, account_id: UUID) -> PlatformAccountConfig:
        account = self.get_account(account_id)
        if account.status != PlatformAccountStatus.ACTIVE:
            raise PlatformAccountError("Platform account is not ACTIVE")
        token_reference = account.token_reference or "FACEBOOK_PAGE_ACCESS_TOKEN"
        access_token = self._resolve_access_token(token_reference)
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

    def _default_workspace_id(self) -> UUID:
        workspace = self.db.scalar(select(Workspace).order_by(Workspace.created_at.asc()).limit(1))
        if workspace is None:
            raise PlatformAccountError("Default workspace not found")
        return workspace.id

    def _resolve_access_token(self, token_reference: str) -> str | None:
        access_token = os.environ.get(token_reference)
        if access_token:
            return access_token

        for env_path in self._candidate_env_paths():
            token = self._read_env_value(env_path, token_reference)
            if token:
                return token
        return None

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
