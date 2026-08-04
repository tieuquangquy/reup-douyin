"""Idempotently import an approved adaptive final into canonical DB boundaries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from src.enums import (
    MediaAssetStatus,
    MediaAssetType,
    RenderOutputStatus,
    ReupQueueMediaPrepStatus,
    ReupQueueStatus,
    SourceVideoStatus,
)
from src.models.export_handoff import ExportPackageItem
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset, RenderOutput
from src.models.reup_queue import ReupQueueItem
from src.render_pipeline.services.video_probe_service import VideoProbeService
from src.services.export_handoff_service import ExportHandoffService
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend
from src.storage.path_strategy import VideoStorageContext, asset_logical_key


class AdaptiveFinalDbHandoffError(RuntimeError):
    pass


_HANDOFF_SCHEMA_VERSION = "adaptive_final_db_handoff_v2"
_RECIPE_LOCK_SCHEMA_VERSION = "pipeline_recipe_lock_v3"
_RECIPE_LOCK_REF_SCHEMA_VERSION = "pipeline_recipe_lock_ref_v1"
_ACCEPTED_RECIPE_LOCK_STATUSES = {
    "LOCKED_FOR_CONTROLLED_PILOT",
    "LOCKED_FOR_CONTROLLED_PILOT_WITH_GAPS",
}
_DOWNSTREAM_QUEUE_STATUSES = {
    ReupQueueStatus.READY_TO_PUBLISH,
    ReupQueueStatus.PUBLISH_HANDOFF_CREATED,
    ReupQueueStatus.COMPLETED,
    ReupQueueStatus.CANCELLED,
}


@dataclass(frozen=True)
class AdaptiveFinalAuthority:
    root: Path
    final_video: Path
    final_video_sha256: str
    final_approval_sha256: str
    local_manifest_sha256: str
    source_video_id: str
    source_video_external_id: str
    render_meta: dict[str, Any]
    output_qa: dict[str, Any]


@dataclass(frozen=True)
class LockedRecipeAuthority:
    source_path: Path
    schema_version: str
    release_label: str
    recipe_sha256: str
    file_sha256: str
    status: str
    validation_boundary: str

    def reference(self) -> dict[str, Any]:
        """Return the canonical, portable recipe reference persisted at every boundary."""

        return {
            "schema_version": _RECIPE_LOCK_REF_SCHEMA_VERSION,
            "artifact_name": self.source_path.name,
            "release_label": self.release_label,
            "recipe_sha256": self.recipe_sha256,
            "file_sha256": self.file_sha256,
            "status": self.status,
            "validation_boundary": self.validation_boundary,
        }


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdaptiveFinalDbHandoffError(f"Cannot read valid {path.name}") from exc
    if not isinstance(payload, dict):
        raise AdaptiveFinalDbHandoffError(f"{path.name} must contain an object")
    return payload


def _verify_self_hash(payload: dict[str, Any], field: str, label: str) -> str:
    claimed = str(payload.get(field) or "")
    unsigned = dict(payload)
    unsigned.pop(field, None)
    if len(claimed) != 64 or _sha256_json(unsigned) != claimed:
        raise AdaptiveFinalDbHandoffError(f"{label} self-hash is invalid")
    return claimed


def load_locked_recipe_authority(
    recipe_lock_path: str | Path,
    *,
    expected_release_label: str,
) -> LockedRecipeAuthority:
    path = Path(recipe_lock_path).resolve()
    if not path.is_file():
        raise AdaptiveFinalDbHandoffError("Locked pipeline recipe was not found")
    payload = _load_object(path)
    recipe_sha256 = _verify_self_hash(payload, "recipe_sha256", "Pipeline recipe lock")
    schema_version = str(payload.get("schema_version") or "")
    if schema_version != _RECIPE_LOCK_SCHEMA_VERSION:
        raise AdaptiveFinalDbHandoffError(
            f"Pipeline recipe lock schema must be {_RECIPE_LOCK_SCHEMA_VERSION}"
        )
    release_label = str(payload.get("release_label") or "")
    if not expected_release_label or release_label != expected_release_label:
        raise AdaptiveFinalDbHandoffError(
            "Pipeline recipe release does not match the expected release"
        )
    status = str(payload.get("status") or "")
    if status not in _ACCEPTED_RECIPE_LOCK_STATUSES:
        raise AdaptiveFinalDbHandoffError("Pipeline recipe is not locked for a pilot")
    claims = dict(payload.get("claims") or {})
    try:
        phase4_case_count = int(
            claims.get("phase4_preflight_case_count") or 0
        )
    except (TypeError, ValueError) as exc:
        raise AdaptiveFinalDbHandoffError(
            "Pipeline recipe Phase 4 preflight count is invalid"
        ) from exc
    closeout = dict(
        dict(payload.get("evidence") or {}).get("phase4_preflight_closeout") or {}
    )
    e2e = dict(dict(payload.get("evidence") or {}).get("e2e_report") or {})
    try:
        closeout_case_count = int(closeout.get("case_count") or 0)
    except (TypeError, ValueError) as exc:
        raise AdaptiveFinalDbHandoffError(
            "Pipeline recipe Phase 4 closeout count is invalid"
        ) from exc
    try:
        e2e_case_count = int(e2e.get("case_count") or 0)
    except (TypeError, ValueError) as exc:
        raise AdaptiveFinalDbHandoffError(
            "Pipeline recipe E2E case count is invalid"
        ) from exc
    claims = dict(payload.get("claims") or {})
    full_e2e_phase4_evidence = (
        claims.get("full_batch_end_to_end_pass") is True
        and e2e_case_count == phase4_case_count
        and e2e_case_count > 0
    )
    if (
        claims.get("controlled_pilot_ready_through_phase4_preflight") is not True
        or phase4_case_count <= 0
        or (
            closeout_case_count != phase4_case_count
            and not full_e2e_phase4_evidence
        )
    ):
        raise AdaptiveFinalDbHandoffError(
            "Pipeline recipe lacks matching Phase 4 preflight evidence"
        )
    if dict(payload.get("execution") or {}).get("external_publish") is not False:
        raise AdaptiveFinalDbHandoffError(
            "Pipeline recipe must keep external publishing disabled"
        )
    return LockedRecipeAuthority(
        source_path=path,
        schema_version=schema_version,
        release_label=release_label,
        recipe_sha256=recipe_sha256,
        file_sha256=_sha256_file(path),
        status=status,
        validation_boundary="PHASE4_PREFLIGHT",
    )


def load_adaptive_final_authority(
    root_dir: str | Path,
    *,
    expected_source_video_id: UUID | str,
) -> AdaptiveFinalAuthority:
    root = Path(root_dir).resolve()
    handoff = _load_object(root / "phase5_export_handoff.json")
    package_relative = str(dict(handoff.get("package") or {}).get("path") or "")
    package_root = (root / package_relative).resolve()
    if not package_root.is_relative_to(root) or not package_root.is_dir():
        raise AdaptiveFinalDbHandoffError("Local export package path is invalid")
    manifest = _load_object(package_root / "manifest.json")
    manifest_sha256 = _verify_self_hash(
        manifest, "manifest_sha256", "Local export manifest"
    )
    if (
        manifest_sha256
        != str(dict(handoff.get("package") or {}).get("manifest_sha256") or "")
    ):
        raise AdaptiveFinalDbHandoffError("Local handoff manifest reference is stale")
    for name, raw_ref in dict(manifest.get("items") or {}).items():
        ref = dict(raw_ref or {})
        path = (package_root / str(ref.get("path") or "")).resolve()
        if (
            not path.is_relative_to(package_root)
            or not path.is_file()
            or path.stat().st_size != int(ref.get("size_bytes") or -1)
            or _sha256_file(path) != str(ref.get("sha256") or "")
        ):
            raise AdaptiveFinalDbHandoffError(f"Local package item is invalid: {name}")

    final_approval = _load_object(root / "phase5_final_approval.json")
    final_approval_sha256 = _verify_self_hash(
        final_approval, "approval_sha256", "Final approval"
    )
    if str(final_approval.get("status") or "") != "FINAL_APPROVED":
        raise AdaptiveFinalDbHandoffError("Final approval is missing")
    source_ref = dict(final_approval.get("source_video") or {})
    if str(source_ref.get("id") or "") != str(expected_source_video_id):
        raise AdaptiveFinalDbHandoffError("Final approval belongs to another source video")
    metadata_approval = _load_object(root / "phase5_metadata_approval.json")
    rights_approval = _load_object(root / "phase5_rights_music_approval.json")
    if str(metadata_approval.get("status") or "") != "METADATA_APPROVED":
        raise AdaptiveFinalDbHandoffError("Metadata approval is missing")
    if (
        str(rights_approval.get("status") or "")
        != "SOURCE_RIGHTS_AND_MUSIC_APPROVED"
    ):
        raise AdaptiveFinalDbHandoffError("Source rights and music approval is missing")
    _verify_self_hash(metadata_approval, "approval_sha256", "Metadata approval")
    _verify_self_hash(rights_approval, "approval_sha256", "Rights approval")

    final_video = root / "phase4_adaptive_final.mp4"
    final_video_sha256 = _sha256_file(final_video)
    approved_video_ref = dict(dict(final_approval.get("refs") or {}).get("final_video") or {})
    package_video_ref = dict(dict(manifest.get("items") or {}).get("video") or {})
    if (
        final_video_sha256 != str(approved_video_ref.get("sha256") or "")
        or final_video_sha256 != str(package_video_ref.get("sha256") or "")
    ):
        raise AdaptiveFinalDbHandoffError("Final video hash does not match approvals")
    render_meta = _load_object(root / "phase4_adaptive_render_meta.json")
    output_qa = _load_object(root / "qa" / "phase4_adaptive_final_output_qa.json")
    if (
        str(render_meta.get("status") or "") != "FINAL_RENDERED"
        or str(render_meta.get("output_qa_status") or "") != "PASS"
        or str(render_meta.get("output_video_sha256") or "") != final_video_sha256
        or str(output_qa.get("status") or "") != "PASS"
        or list(output_qa.get("failed_checks") or [])
    ):
        raise AdaptiveFinalDbHandoffError("Adaptive final encoded-output QA is not PASS")
    return AdaptiveFinalAuthority(
        root=root,
        final_video=final_video,
        final_video_sha256=final_video_sha256,
        final_approval_sha256=final_approval_sha256,
        local_manifest_sha256=manifest_sha256,
        source_video_id=str(source_ref.get("id") or ""),
        source_video_external_id=str(source_ref.get("external_id") or ""),
        render_meta=render_meta,
        output_qa=output_qa,
    )


class AdaptiveFinalDbHandoffService:
    def __init__(
        self,
        db: Session,
        *,
        storage: StorageBackend,
    ) -> None:
        self.db = db
        self.storage = storage
        self.probe_service = VideoProbeService(storage)

    def import_final(
        self,
        *,
        root_dir: str | Path,
        source_video_id: UUID,
        queue_item_id: UUID | None = None,
        create_export_package: bool = True,
        recipe_lock_path: str | Path,
        expected_recipe_release: str,
    ) -> dict[str, Any]:
        recipe = load_locked_recipe_authority(
            recipe_lock_path,
            expected_release_label=expected_recipe_release,
        )
        recipe_ref = recipe.reference()
        authority = load_adaptive_final_authority(
            root_dir,
            expected_source_video_id=source_video_id,
        )
        source = self.db.scalar(
            select(SourceVideo)
            .where(SourceVideo.id == source_video_id)
            .options(selectinload(SourceVideo.source_profile))
        )
        if source is None:
            raise AdaptiveFinalDbHandoffError("Source video was not found in DB")
        if source.source_video_external_id != authority.source_video_external_id:
            raise AdaptiveFinalDbHandoffError("Source external id does not match authority")
        queue_item = self._resolve_queue_item(source_video_id, queue_item_id)
        if queue_item.workspace_id != source.workspace_id:
            raise AdaptiveFinalDbHandoffError("Queue item workspace does not match source")

        existing_assets = list(
            self.db.scalars(
                select(MediaAsset).where(
                    MediaAsset.source_video_id == source_video_id,
                    MediaAsset.asset_type == MediaAssetType.FINAL_RENDER_VIDEO,
                )
            )
        )
        asset = next(
            (
                item
                for item in existing_assets
                if item.checksum_sha256 == authority.final_video_sha256
            ),
            None,
        )
        asset_reused = asset is not None
        if asset is None:
            for item in existing_assets:
                item.is_current = False
            context = self._storage_context(source)
            logical_key = asset_logical_key(
                context,
                MediaAssetType.FINAL_RENDER_VIDEO,
                filename=(
                    f"adaptive_phase4_{authority.final_video_sha256[:12]}_final.mp4"
                ),
            )
            written = self.storage.write_bytes(
                logical_key, authority.final_video.read_bytes()
            )
            if written.checksum_sha256 != authority.final_video_sha256:
                raise AdaptiveFinalDbHandoffError("Stored final video checksum mismatch")
            asset = MediaAsset(
                workspace_id=source.workspace_id,
                source_video_id=source.id,
                asset_type=MediaAssetType.FINAL_RENDER_VIDEO,
                status=MediaAssetStatus.AVAILABLE,
                version=max((item.version for item in existing_assets), default=0) + 1,
                storage_provider=written.storage_provider,
                storage_key=written.storage_key,
                logical_key=logical_key,
                relative_path=written.relative_path,
                manifest_group="adaptive_phase4_import",
                is_current=True,
                mime_type="video/mp4",
                size_bytes=written.size_bytes,
                checksum_sha256=written.checksum_sha256,
                metadata_json={
                    "adaptive_final_import": {
                        "schema_version": _HANDOFF_SCHEMA_VERSION,
                        "final_video_sha256": authority.final_video_sha256,
                        "final_approval_sha256": authority.final_approval_sha256,
                        "local_manifest_sha256": authority.local_manifest_sha256,
                        "recipe_lock": recipe_ref,
                    },
                    "adaptive_final_recipe_refs": {
                        recipe.recipe_sha256: recipe_ref,
                    },
                },
            )
            self.db.add(asset)
            self.db.flush()
        else:
            asset.is_current = True
            stored = self.storage.metadata(asset.storage_key)
            if (
                not stored.exists
                or stored.checksum_sha256 != authority.final_video_sha256
            ):
                raise AdaptiveFinalDbHandoffError("Existing DB media asset is unavailable")
            asset_metadata = dict(asset.metadata_json or {})
            asset_import = dict(asset_metadata.get("adaptive_final_import") or {})
            asset_import.update(
                {
                    "schema_version": _HANDOFF_SCHEMA_VERSION,
                    "final_video_sha256": authority.final_video_sha256,
                    "final_approval_sha256": authority.final_approval_sha256,
                    "local_manifest_sha256": authority.local_manifest_sha256,
                    "recipe_lock": recipe_ref,
                }
            )
            recipe_refs = dict(asset_metadata.get("adaptive_final_recipe_refs") or {})
            recipe_refs[recipe.recipe_sha256] = recipe_ref
            asset.metadata_json = {
                **asset_metadata,
                "adaptive_final_import": asset_import,
                "adaptive_final_recipe_refs": recipe_refs,
            }
        for item in existing_assets:
            item.is_current = item.id == asset.id

        render_contract_path = authority.root / "phase4_render_input.json"
        render_contract = (
            _load_object(render_contract_path) if render_contract_path.is_file() else None
        )
        subtitle_burned = (
            bool(list(render_contract.get("render_tracks") or []))
            if render_contract is not None
            else True
        )
        audio_strategy = str(
            dict(authority.render_meta.get("audio_mix") or {}).get("strategy")
            or "joined_vietnamese_tts_with_background_stem"
        )
        existing_renders = list(
            self.db.scalars(
                select(RenderOutput).where(RenderOutput.source_video_id == source_video_id)
            )
        )
        render = next(
            (
                item
                for item in existing_renders
                if self._render_matches(item, authority, recipe)
            ),
            None,
        )
        render_reused = render is not None
        probe = self.probe_service.probe(asset.storage_key)
        now = datetime.now(UTC)
        if render is None:
            render = RenderOutput(
                workspace_id=source.workspace_id,
                source_video_id=source.id,
                media_asset_id=asset.id,
                status=RenderOutputStatus.APPROVED,
                target_platform="FACEBOOK_REELS",
                version=max((item.version for item in existing_renders), default=0) + 1,
                render_type="adaptive_phase4",
                output_format="mp4",
                width=probe.width,
                height=probe.height,
                fps=probe.fps,
                duration_seconds=probe.duration_seconds,
                video_codec=probe.video_codec,
                audio_codec=probe.audio_codec,
                subtitle_burned=subtitle_burned,
                audio_strategy=audio_strategy,
                render_version=(
                    "ADAPTIVE_PHASE4_"
                    f"{authority.final_video_sha256[:8]}_{recipe.recipe_sha256[:8]}"
                ),
                warning_summary_json={"warnings": []},
                started_at=now,
                finished_at=now,
                render_settings_json={
                    "authority": "phase4_render_recipe.json",
                    "geometry_transform": "none",
                    "invisible_perturbation": False,
                    "recipe_lock": recipe_ref,
                },
                metadata_json=self._render_metadata(authority, recipe, now),
            )
            self.db.add(render)
            self.db.flush()
        else:
            render.media_asset_id = asset.id
            render.status = RenderOutputStatus.APPROVED
            render.subtitle_burned = subtitle_burned
            render.audio_strategy = audio_strategy
            render.metadata_json = {
                **(render.metadata_json or {}),
                **self._render_metadata(authority, recipe, now),
            }
            render_settings = dict(getattr(render, "render_settings_json", None) or {})
            render_settings["recipe_lock"] = recipe_ref
            render.render_settings_json = render_settings

        previous_render_output_id = queue_item.render_output_id
        if (
            queue_item.status in _DOWNSTREAM_QUEUE_STATUSES
            and previous_render_output_id is not None
            and previous_render_output_id != render.id
        ):
            raise AdaptiveFinalDbHandoffError(
                "Downstream queue item is already bound to another render output"
            )

        if source.status != SourceVideoStatus.EXPORTED:
            source.status = SourceVideoStatus.PUBLISH_READY
        queue_item.render_output_id = render.id
        queue_item.media_prep_status = ReupQueueMediaPrepStatus.READY_FOR_EXPORT
        queue_item.media_ready_at = queue_item.media_ready_at or now
        queue_item.blocked_at = None
        queue_item.blocked_reason = None
        queue_item.failed_at = None
        queue_item.last_error_code = None
        queue_item.last_error_message = None
        queue_item.last_action_at = now
        queue_item.last_action_note = "Approved adaptive final imported; ready for export."
        queue_item.metadata_json = {
            **(queue_item.metadata_json or {}),
            "adaptive_final_import": {
                "schema_version": _HANDOFF_SCHEMA_VERSION,
                "final_video_sha256": authority.final_video_sha256,
                "final_approval_sha256": authority.final_approval_sha256,
                "local_manifest_sha256": authority.local_manifest_sha256,
                "recipe_lock": recipe_ref,
                "render_output_id": str(render.id),
                "imported_at": now.isoformat(),
            },
            "render_qa": {
                "status": "pass",
                "summary": "Adaptive encoded-output QA PASS",
                "failed": [],
                "warned": [],
            },
        }

        package = self._existing_export_package(queue_item.id, render.id, recipe)
        package_reused = package is not None
        if (
            create_export_package
            and package is None
            and queue_item.status in _DOWNSTREAM_QUEUE_STATUSES
        ):
            raise AdaptiveFinalDbHandoffError(
                "Downstream queue item has no ExportPackage for the locked recipe"
            )
        if package is None:
            queue_item.metadata_json.pop("export_package_id", None)
        if queue_item.status not in _DOWNSTREAM_QUEUE_STATUSES:
            queue_item.status = (
                ReupQueueStatus.EXPORT_PACKAGE_CREATED
                if package is not None
                else ReupQueueStatus.READY_TO_EXPORT
            )
        if package is not None:
            queue_item.metadata_json = {
                **(queue_item.metadata_json or {}),
                "export_package_id": str(package.id),
            }
        self.db.commit()

        adaptive_manifest_import = {
            "schema_version": _HANDOFF_SCHEMA_VERSION,
            "render_output_id": str(render.id),
            "final_video_sha256": authority.final_video_sha256,
            "local_manifest_sha256": authority.local_manifest_sha256,
            "recipe_lock": recipe_ref,
        }
        if create_export_package and package is None:
            package, result = ExportHandoffService(self.db).create_export_package(
                item_ids=[queue_item.id],
                label=f"Adaptive final {authority.source_video_external_id}",
                operator_note="Hash-verified adaptive local pilot import.",
                package_manifest_extension={
                    "adaptive_final_import": adaptive_manifest_import,
                },
                item_manifest_extension={
                    "adaptive_final_import": adaptive_manifest_import,
                },
            )
            if result.succeeded_count != 1:
                raise AdaptiveFinalDbHandoffError("DB ExportPackage creation failed")
        if package is not None:
            package.manifest_json = {
                **(package.manifest_json or {}),
                "adaptive_final_import": adaptive_manifest_import,
            }
            package.diagnostics_json = {
                **(package.diagnostics_json or {}),
                "external_publish_triggered": False,
            }
            if queue_item.status not in _DOWNSTREAM_QUEUE_STATUSES:
                queue_item.status = ReupQueueStatus.EXPORT_PACKAGE_CREATED
            queue_item.metadata_json = {
                **(queue_item.metadata_json or {}),
                "export_package_id": str(package.id),
            }
            package_item = self._find_export_package_item(
                queue_item.id, render.id, package.id
            )
            if package_item is None:
                raise AdaptiveFinalDbHandoffError(
                    "DB ExportPackage item is missing after creation"
                )
            package_item.manifest_json = {
                **(package_item.manifest_json or {}),
                "adaptive_final_import": adaptive_manifest_import,
            }
            package_item.diagnostics_json = {
                **(package_item.diagnostics_json or {}),
                "recipe_lock": recipe_ref,
            }
            self.db.commit()
        return {
            "schema_version": _HANDOFF_SCHEMA_VERSION,
            "status": "DB_EXPORT_PACKAGE_READY" if package is not None else "DB_RENDER_READY",
            "source_video_id": str(source.id),
            "queue_item_id": str(queue_item.id),
            "media_asset_id": str(asset.id),
            "render_output_id": str(render.id),
            "export_package_id": str(package.id) if package is not None else None,
            "final_video_sha256": authority.final_video_sha256,
            "final_approval_sha256": authority.final_approval_sha256,
            "local_manifest_sha256": authority.local_manifest_sha256,
            "recipe_lock": recipe_ref,
            "asset_reused": asset_reused,
            "render_reused": render_reused,
            "export_package_reused": package_reused,
            "retry_safe": True,
            "external_publish_triggered": False,
        }

    def _resolve_queue_item(
        self, source_video_id: UUID, queue_item_id: UUID | None
    ) -> ReupQueueItem:
        if queue_item_id is not None:
            item = self.db.get(ReupQueueItem, queue_item_id)
        else:
            item = self.db.scalar(
                select(ReupQueueItem)
                .where(ReupQueueItem.source_video_id == source_video_id)
                .order_by(ReupQueueItem.created_at.desc())
                .limit(1)
            )
        if item is None or item.source_video_id != source_video_id:
            raise AdaptiveFinalDbHandoffError("Matching Reup Queue item was not found")
        return item

    def _existing_export_package(
        self,
        queue_item_id: UUID,
        render_output_id: UUID,
        recipe: LockedRecipeAuthority,
    ) -> Any | None:
        items = self.db.scalars(
            select(ExportPackageItem)
            .where(
                ExportPackageItem.reup_queue_item_id == queue_item_id,
                ExportPackageItem.render_output_id == render_output_id,
            )
            .options(selectinload(ExportPackageItem.export_package))
        )
        for item in items:
            package = item.export_package
            package_import = dict(
                dict(package.manifest_json or {}).get("adaptive_final_import") or {}
            )
            if self._recipe_ref_matches(
                package_import.get("recipe_lock"), recipe
            ):
                return package
        return None

    def _find_export_package_item(
        self,
        queue_item_id: UUID,
        render_output_id: UUID,
        package_id: UUID | None,
    ) -> ExportPackageItem | None:
        statement = select(ExportPackageItem).where(
            ExportPackageItem.reup_queue_item_id == queue_item_id,
            ExportPackageItem.render_output_id == render_output_id,
        )
        if package_id is not None:
            statement = statement.where(
                ExportPackageItem.export_package_id == package_id
            )
        return self.db.scalar(statement)

    @staticmethod
    def _recipe_ref_matches(
        raw_ref: Any, recipe: LockedRecipeAuthority
    ) -> bool:
        recipe_ref = dict(raw_ref or {})
        return (
            str(recipe_ref.get("schema_version") or "")
            == _RECIPE_LOCK_REF_SCHEMA_VERSION
            and (
                str(recipe_ref.get("recipe_sha256") or "")
                == recipe.recipe_sha256
                or str(recipe_ref.get("release_label") or "")
                == recipe.release_label
            )
        )

    def _render_matches(
        self,
        render: RenderOutput,
        authority: AdaptiveFinalAuthority,
        recipe: LockedRecipeAuthority,
    ) -> bool:
        imported = dict(
            dict(render.metadata_json or {}).get("adaptive_final_import") or {}
        )
        return (
            str(imported.get("final_video_sha256") or "")
            == authority.final_video_sha256
            and self._recipe_ref_matches(
                imported.get("recipe_lock"), recipe
            )
        )

    def _storage_context(self, source: SourceVideo) -> VideoStorageContext:
        profile = source.source_profile
        return VideoStorageContext(
            workspace_id=str(source.workspace_id),
            source_platform=source.source_platform,
            source_profile_external_id=profile.source_profile_external_id,
            source_video_external_id=source.source_video_external_id,
            profile_handle=getattr(profile, "handle", None),
            profile_display_name=getattr(profile, "display_name", None),
        )

    def _render_metadata(
        self,
        authority: AdaptiveFinalAuthority,
        recipe: LockedRecipeAuthority,
        now: datetime,
    ) -> dict[str, Any]:
        return {
            "adaptive_final_import": {
                "schema_version": _HANDOFF_SCHEMA_VERSION,
                "final_video_sha256": authority.final_video_sha256,
                "final_approval_sha256": authority.final_approval_sha256,
                "local_manifest_sha256": authority.local_manifest_sha256,
                "output_qa_status": "PASS",
                "recipe_lock": recipe.reference(),
                "imported_at": now.isoformat(),
            },
            "final_review": {
                "approved_at": now.isoformat(),
                "publish_ready_at": now.isoformat(),
                "approval_source": "hash_verified_local_final_approval",
            },
        }


def build_default_adaptive_final_db_handoff_service(
    db: Session,
) -> AdaptiveFinalDbHandoffService:
    from src.core.settings import get_settings

    return AdaptiveFinalDbHandoffService(
        db,
        storage=LocalStorageBackend(get_settings().local_storage_root),
    )
