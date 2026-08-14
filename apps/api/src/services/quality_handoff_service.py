from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import PublishTargetPlatform, ReupQueueStatus
from src.models.ingestion import SourceVideo
from src.models.reup_queue import ReupQueueItem
from src.services.export_handoff_service import ExportHandoffService
from src.services.local_final_handoff import (
    LocalFinalHandoffError,
    approve_local_publish_metadata,
    approve_local_source_rights_and_music,
    create_local_final_handoff,
    finalize_local_manual_export,
    update_local_publish_metadata,
)
from src.services.quality_localization_service import (
    QualityLocalizationError,
    QualityLocalizationService,
)
from src.storage.local import LocalStorageBackend
from src.core.settings import get_settings


class QualityHandoffError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


class QualityHandoffService:
    """DB/API boundary for the hash-bound local Phase-5 handoff.

    The artifact implementation remains in ``local_final_handoff``.  This
    facade exposes idempotent product actions and synchronizes the completed
    manual package into ExportPackage/PublishHandoff records without granting
    or triggering external publication.
    """

    def __init__(
        self,
        db: Session,
        *,
        storage: LocalStorageBackend | None = None,
    ) -> None:
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)

    def summary(self, source_video_id: UUID) -> dict[str, Any]:
        source = self._source(source_video_id)
        try:
            root = QualityLocalizationService(
                self.db, storage=self.storage
            ).active_root(source.id)
        except QualityLocalizationError:
            return self._empty_summary(source.id)

        final_approval = _read_object(root / "phase5_final_approval.json")
        export_handoff = _read_object(root / "phase5_export_handoff.json")
        metadata_approval = _read_object(root / "phase5_metadata_approval.json")
        rights_approval = _read_object(root / "phase5_rights_music_approval.json")
        manual_handoff = _read_object(root / "phase5_manual_export_handoff.json")
        package_root = self._package_root(root, export_handoff)
        publish_draft = (
            _read_object(package_root / "publish_draft.json")
            if package_root is not None
            else {}
        )
        archive = dict(manual_handoff.get("archive") or {})
        archive_path = str(archive.get("path") or "") or None
        db_binding = self._db_binding(source.id)
        return {
            "source_video_id": str(source.id),
            "workflow_version": "QUALITY_LOCALIZATION_V24_1",
            "artifact_run_id": root.name,
            "final_approval_status": str(final_approval.get("status") or "NOT_READY"),
            "metadata_status": str(
                metadata_approval.get("status")
                or publish_draft.get("status")
                or "NOT_READY"
            ),
            "rights_status": str(rights_approval.get("status") or "NOT_READY"),
            "manual_export_status": str(manual_handoff.get("status") or "NOT_READY"),
            "handoff_status": str(export_handoff.get("status") or "NOT_READY"),
            "next_gate": export_handoff.get("next_gate"),
            "publish_authorization_status": export_handoff.get(
                "publish_authorization_status"
            ),
            "external_publish_triggered": bool(
                export_handoff.get("external_publish_triggered")
                or manual_handoff.get("external_publish_triggered")
            ),
            "publish_draft": publish_draft or None,
            "archive_path": archive_path,
            "archive_sha256": archive.get("sha256"),
            "archive_size_bytes": archive.get("size_bytes"),
            "export_package_id": db_binding.get("export_package_id"),
            "publish_handoff_id": db_binding.get("publish_handoff_id"),
        }

    def approve_final(
        self,
        source_video_id: UUID,
        *,
        operator_id: str,
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        root = self._root(source.id)
        existing = _read_object(root / "phase5_export_handoff.json")
        if not existing:
            try:
                create_local_final_handoff(
                    root_dir=root,
                    source_video_id=str(source.id),
                    source_video_external_id=source.source_video_external_id,
                    operator_id=operator_id,
                )
            except LocalFinalHandoffError as exc:
                raise QualityHandoffError(str(exc)) from exc
        return self.summary(source.id)

    def approve_metadata(
        self,
        source_video_id: UUID,
        *,
        operator_id: str,
        target_platform: str,
        title: str,
        caption: str,
        cta_text: str,
        hashtags: list[str],
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        root = self._root(source.id)
        try:
            update_local_publish_metadata(
                root_dir=root,
                target_platform=target_platform,
                title=title,
                caption=caption,
                cta_text=cta_text,
                hashtags=hashtags,
                generation_source="frontend_operator_v1",
            )
            approve_local_publish_metadata(root_dir=root, operator_id=operator_id)
        except (LocalFinalHandoffError, ValueError) as exc:
            raise QualityHandoffError(str(exc)) from exc
        return self.summary(source.id)

    def approve_rights(
        self,
        source_video_id: UUID,
        *,
        operator_id: str,
        source_video_reuse_authorized: bool,
        retained_music_use_authorized: bool,
        operator_accepts_responsibility: bool,
    ) -> dict[str, Any]:
        if not all(
            (
                source_video_reuse_authorized,
                retained_music_use_authorized,
                operator_accepts_responsibility,
            )
        ):
            raise QualityHandoffError(
                "All source-rights and retained-music attestations are required"
            )
        source = self._source(source_video_id)
        root = self._root(source.id)
        try:
            approve_local_source_rights_and_music(
                root_dir=root,
                operator_id=operator_id,
                attestation_overrides={
                    "source_video_reuse_authorized": source_video_reuse_authorized,
                    "retained_music_use_on_target_platform_authorized": retained_music_use_authorized,
                    "operator_accepts_responsibility_for_rights_claim": operator_accepts_responsibility,
                },
                evidence_overrides={
                    "source": "frontend_explicit_operator_attestation",
                },
            )
        except LocalFinalHandoffError as exc:
            raise QualityHandoffError(str(exc)) from exc
        return self.summary(source.id)

    def finalize_manual_export(
        self,
        source_video_id: UUID,
        *,
        operator_id: str,
    ) -> dict[str, Any]:
        source = self._source(source_video_id)
        root = self._root(source.id)
        try:
            result = finalize_local_manual_export(
                root_dir=root,
                operator_id=operator_id,
            )
        except LocalFinalHandoffError as exc:
            raise QualityHandoffError(str(exc)) from exc
        self._sync_db_handoff(source, root=root, result=result, operator_id=operator_id)
        self.db.commit()
        return self.summary(source.id)

    def _sync_db_handoff(
        self,
        source: SourceVideo,
        *,
        root: Path,
        result: dict[str, Any],
        operator_id: str,
    ) -> None:
        items = list(
            self.db.scalars(
                select(ReupQueueItem).where(
                    ReupQueueItem.source_video_id == source.id
                )
            ).all()
        )
        if not items:
            return
        already_bound = [
            item
            for item in items
            if str(dict(item.metadata_json or {}).get("quality_manual_export_archive") or "")
        ]
        archive_path = Path(result["archive_path"]).resolve()
        archive_relative = archive_path.relative_to(self.storage.root).as_posix()
        if already_bound:
            return
        eligible = [item for item in items if item.status == ReupQueueStatus.READY_TO_EXPORT]
        if not eligible:
            raise QualityHandoffError(
                "Final Review must mark the render publish-ready before manual export"
            )
        export_service = ExportHandoffService(self.db)
        package, batch = export_service.create_export_package(
            item_ids=[item.id for item in eligible],
            label=f"Manual export {source.source_video_external_id}",
            operator_note="Hash-verified quality manual export",
            package_manifest_extension={
                "quality_artifact_root": root.relative_to(self.storage.root).as_posix(),
                "quality_manual_export_archive": archive_relative,
            },
            item_manifest_extension={
                "quality_manual_export_archive": archive_relative,
            },
        )
        if batch.succeeded_count <= 0:
            raise QualityHandoffError("No Reup Queue item was eligible for export")
        handoff = export_service.create_publish_handoff(
            export_package_id=package.id,
            target_platform=PublishTargetPlatform.FACEBOOK_REELS,
            operator_note="Manual upload only; external publish is not authorized",
        )
        for item in eligible:
            item.metadata_json = {
                **dict(item.metadata_json or {}),
                "quality_manual_export_archive": archive_relative,
                "quality_manual_export_package_id": str(package.id),
                "quality_manual_publish_handoff_id": str(handoff.id),
                "quality_manual_export_operator_id": operator_id,
            }

    def _db_binding(self, source_video_id: UUID) -> dict[str, str | None]:
        item = self.db.scalar(
            select(ReupQueueItem)
            .where(ReupQueueItem.source_video_id == source_video_id)
            .order_by(ReupQueueItem.updated_at.desc())
            .limit(1)
        )
        metadata = dict(item.metadata_json or {}) if item is not None else {}
        return {
            "export_package_id": metadata.get("quality_manual_export_package_id"),
            "publish_handoff_id": metadata.get("quality_manual_publish_handoff_id"),
        }

    def _source(self, source_video_id: UUID) -> SourceVideo:
        source = self.db.get(SourceVideo, source_video_id)
        if source is None:
            raise QualityHandoffError("Source video was not found")
        return source

    def _root(self, source_video_id: UUID) -> Path:
        try:
            return QualityLocalizationService(
                self.db, storage=self.storage
            ).active_root(source_video_id)
        except QualityLocalizationError as exc:
            raise QualityHandoffError(str(exc)) from exc

    @staticmethod
    def _package_root(root: Path, handoff: dict[str, Any]) -> Path | None:
        relative = str(dict(handoff.get("package") or {}).get("path") or "")
        if not relative:
            return None
        candidate = (root / relative).resolve()
        if not candidate.is_relative_to(root) or not candidate.is_dir():
            return None
        return candidate

    @staticmethod
    def _empty_summary(source_video_id: UUID) -> dict[str, Any]:
        return {
            "source_video_id": str(source_video_id),
            "workflow_version": "QUALITY_LOCALIZATION_V24_1",
            "artifact_run_id": None,
            "final_approval_status": "NOT_READY",
            "metadata_status": "NOT_READY",
            "rights_status": "NOT_READY",
            "manual_export_status": "NOT_READY",
            "handoff_status": "NOT_READY",
            "next_gate": None,
            "publish_authorization_status": None,
            "external_publish_triggered": False,
            "publish_draft": None,
            "archive_path": None,
            "archive_sha256": None,
            "archive_size_bytes": None,
            "export_package_id": None,
            "publish_handoff_id": None,
        }
