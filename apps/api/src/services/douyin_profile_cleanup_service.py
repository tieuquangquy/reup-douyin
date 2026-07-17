from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.source_accounts import DouyinAccountConnection
from src.schemas.douyin_accounts import (
    DouyinProfileCleanupAccountSummary,
    DouyinProfileCleanupProfileSummary,
    DouyinProfileCleanupResponse,
)
from src.services.douyin_account_service import DouyinAccountService
from src.services.douyin_browser_context_registry import douyin_browser_context_registry


_CONNECT_SESSION_PROFILE_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F-]{36}$")


@dataclass(frozen=True)
class _CanonicalProfile:
    account: DouyinAccountConnection
    profile_id: str
    path_leaf: str
    mapping_action: str
    reason: str
    metadata_update: dict | None = None


class DouyinProfileCleanupService:
    """Safe reconciliation for local Douyin persistent browser profile dirs."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def scan(self, *, apply: bool = False) -> DouyinProfileCleanupResponse:
        settings = get_settings()
        root = Path(settings.douyin_persistent_browser_profiles_root_dir).resolve()
        profile_dirs = self._profile_dirs(root)
        profile_ids = {path.name for path in profile_dirs}
        accounts = self._load_accounts()
        accounts_by_id = {account.id: account for account in accounts}
        active_profile_ids = douyin_browser_context_registry.active_profile_ids()

        canonical_by_profile: dict[str, _CanonicalProfile] = {}
        account_summaries: list[DouyinProfileCleanupAccountSummary] = []
        metadata_updates: list[tuple[DouyinAccountConnection, dict]] = []
        for account in accounts:
            canonical = self._choose_canonical(account=account, profile_ids=profile_ids, root=root)
            if canonical is not None:
                canonical_by_profile[canonical.path_leaf] = canonical
                if canonical.metadata_update is not None:
                    metadata_updates.append((account, canonical.metadata_update))
                account_summaries.append(
                    DouyinProfileCleanupAccountSummary(
                        account_id=account.id,
                        status=account.status,
                        canonical_profile_id=canonical.profile_id,
                        canonical_profile_path_leaf=canonical.path_leaf,
                        mapping_action=canonical.mapping_action,
                        reason=canonical.reason,
                    )
                )
                continue
            metadata = dict(getattr(account, "metadata_json", None) or {})
            reason = "no_profile_metadata_or_account_profile_dir"
            if metadata.get("browser_profile_id") or metadata.get("browser_profile_path"):
                reason = "metadata_profile_missing_on_disk"
            account_summaries.append(
                DouyinProfileCleanupAccountSummary(
                    account_id=account.id,
                    status=account.status,
                    canonical_profile_id=None,
                    canonical_profile_path_leaf=None,
                    mapping_action="no_profile",
                    reason=reason,
                )
            )

        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        quarantine_root = root / "_quarantine" / timestamp
        profile_summaries: list[DouyinProfileCleanupProfileSummary] = []
        quarantine_candidates: list[Path] = []
        for path in sorted(profile_dirs, key=lambda item: item.name):
            leaf = path.name
            last_modified_at = self._last_modified_at(path)
            if leaf in canonical_by_profile:
                canonical = canonical_by_profile[leaf]
                profile_summaries.append(
                    DouyinProfileCleanupProfileSummary(
                        profile_id=canonical.profile_id,
                        path_leaf=leaf,
                        classification="canonical",
                        linked_account_id=canonical.account.id,
                        active=leaf in active_profile_ids,
                        planned_action="keep",
                        reason=canonical.reason,
                        last_modified_at=last_modified_at,
                    )
                )
                continue

            active = leaf in active_profile_ids
            classification, linked_account_id, reason = self._classify_noncanonical(
                leaf=leaf,
                accounts_by_id=accounts_by_id,
            )
            if active:
                profile_summaries.append(
                    DouyinProfileCleanupProfileSummary(
                        profile_id=leaf,
                        path_leaf=leaf,
                        classification="active_in_use",
                        linked_account_id=linked_account_id,
                        active=True,
                        planned_action="skip_active",
                        reason="runtime_registry_reports_profile_active",
                        last_modified_at=last_modified_at,
                    )
                )
                continue

            quarantine_candidates.append(path)
            profile_summaries.append(
                DouyinProfileCleanupProfileSummary(
                    profile_id=leaf,
                    path_leaf=leaf,
                    classification=classification,
                    linked_account_id=linked_account_id,
                    active=False,
                    planned_action="quarantine",
                    reason=reason,
                    quarantine_leaf=f"{timestamp}/{leaf}" if apply else None,
                    last_modified_at=last_modified_at,
                )
            )

        if apply:
            for account, metadata in metadata_updates:
                account.metadata_json = metadata
            moved: dict[str, str] = {}
            for path in quarantine_candidates:
                destination = self._quarantine_path(root=root, quarantine_root=quarantine_root, source=path)
                if destination is None:
                    continue
                moved[path.name] = f"{timestamp}/{destination.name}"
            for summary in profile_summaries:
                if summary.path_leaf in moved:
                    summary.quarantine_leaf = moved[summary.path_leaf]
            if metadata_updates:
                self.db.commit()

        canonical_count = sum(1 for item in profile_summaries if item.classification == "canonical")
        skipped_active_count = sum(1 for item in profile_summaries if item.planned_action == "skip_active")
        duplicate_count = sum(1 for item in profile_summaries if item.classification == "duplicate_noncanonical")
        orphan_count = sum(1 for item in profile_summaries if item.classification == "orphan_unlinked")
        quarantine_count = sum(1 for item in profile_summaries if item.planned_action == "quarantine")
        return DouyinProfileCleanupResponse(
            dry_run=not apply,
            applied=apply,
            profiles_root_leaf=root.name,
            quarantine_root_leaf=f"_quarantine/{timestamp}" if apply and quarantine_candidates else None,
            profiles_scanned=len(profile_summaries),
            accounts_scanned=len(accounts),
            canonical_count=canonical_count,
            orphan_count=orphan_count,
            duplicate_count=duplicate_count,
            quarantine_count=quarantine_count,
            skipped_active_count=skipped_active_count,
            metadata_repairs_count=len(metadata_updates),
            profiles=profile_summaries,
            accounts=account_summaries,
        )

    def _load_accounts(self) -> list[DouyinAccountConnection]:
        return DouyinAccountService(self.db).list_accounts(include_deleted=True)

    def _profile_dirs(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        return [
            item
            for item in root.iterdir()
            if item.is_dir() and not item.name.startswith("_quarantine")
        ]

    def _choose_canonical(
        self,
        *,
        account: DouyinAccountConnection,
        profile_ids: set[str],
        root: Path,
    ) -> _CanonicalProfile | None:
        metadata = dict(getattr(account, "metadata_json", None) or {})
        stored_profile_id = self._clean_profile_id(metadata.get("browser_profile_id"))
        stored_path_leaf = self._path_leaf(metadata.get("browser_profile_path"))
        if stored_profile_id or stored_path_leaf:
            profile_id = stored_profile_id or stored_path_leaf
            path_leaf = stored_path_leaf or profile_id
            if path_leaf in profile_ids:
                metadata_update = None
                action = "keep_existing_profile_metadata"
                reason = "account_metadata_points_to_existing_profile"
                if not stored_profile_id or metadata.get("browser_profile_path") is None:
                    metadata_update = dict(metadata)
                    metadata_update["browser_profile_id"] = profile_id
                    metadata_update["browser_profile_path"] = str(root / path_leaf)
                    metadata_update["browser_profile_mode"] = "persistent_profile"
                    metadata_update["profile_cleanup_reconciled_at"] = datetime.now(UTC).isoformat()
                    action = "repair_existing_profile_metadata"
                    reason = "repaired_missing_profile_id_or_path"
                return _CanonicalProfile(account, profile_id, path_leaf, action, reason, metadata_update)
            return None

        account_profile_id = f"account-{account.id}"
        if account_profile_id not in profile_ids:
            return None
        metadata_update = dict(metadata)
        metadata_update["browser_profile_id"] = account_profile_id
        metadata_update["browser_profile_path"] = str(root / account_profile_id)
        metadata_update["browser_profile_mode"] = "persistent_profile"
        metadata_update["profile_cleanup_reconciled_at"] = datetime.now(UTC).isoformat()
        return _CanonicalProfile(
            account,
            account_profile_id,
            account_profile_id,
            "adopt_account_profile_dir",
            "account_named_profile_dir_exists_without_metadata",
            metadata_update,
        )

    def _classify_noncanonical(
        self,
        *,
        leaf: str,
        accounts_by_id: dict[UUID, DouyinAccountConnection],
    ) -> tuple[str, UUID | None, str]:
        if leaf.startswith("account-"):
            candidate = leaf.removeprefix("account-")
            try:
                account_id = UUID(candidate)
            except ValueError:
                return "orphan_unlinked", None, "invalid_account_profile_name"
            if account_id in accounts_by_id:
                return "duplicate_noncanonical", account_id, "account_profile_not_chosen_as_canonical"
            return "orphan_unlinked", None, "account_profile_has_no_matching_account"
        if _CONNECT_SESSION_PROFILE_RE.match(leaf):
            return "duplicate_noncanonical", None, "old_connect_session_profile"
        return "orphan_unlinked", None, "unlinked_profile_directory"

    def _quarantine_path(self, *, root: Path, quarantine_root: Path, source: Path) -> Path | None:
        resolved_root = root.resolve()
        resolved_source = source.resolve()
        if resolved_source.parent != resolved_root:
            return None
        if not source.exists() or not source.is_dir():
            return None
        quarantine_root.mkdir(parents=True, exist_ok=True)
        destination = quarantine_root / source.name
        suffix = 1
        while destination.exists():
            destination = quarantine_root / f"{source.name}-{suffix}"
            suffix += 1
        shutil.move(str(source), str(destination))
        return destination

    def _last_modified_at(self, path: Path) -> datetime | None:
        try:
            return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        except OSError:
            return None

    def _clean_profile_id(self, value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        return "".join(char if char.isalnum() or char in {"-", "_"} else "-" for char in value)[:120] or None

    def _path_leaf(self, value: object) -> str | None:
        if not isinstance(value, str) or not value:
            return None
        return self._clean_profile_id(Path(value).name)
