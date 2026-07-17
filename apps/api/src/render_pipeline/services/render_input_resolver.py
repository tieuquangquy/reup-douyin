from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.enums import MediaAssetStatus, MediaAssetType
from src.models.media import MediaAsset
from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.types import ResolvedRenderInput
from src.storage.base import StorageBackend


class RenderInputResolver:
    def __init__(self, db: Session, storage: StorageBackend):
        self.db = db
        self.storage = storage

    def resolve(self, source_video_id: UUID) -> ResolvedRenderInput:
        manifest_asset = self._current_asset(source_video_id, MediaAssetType.RENDER_PREP_MANIFEST)
        if manifest_asset is None or not isinstance(manifest_asset.metadata_json, dict):
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_RENDER_PREP_MANIFEST, "Current render-prep manifest is missing")
        manifest = dict(manifest_asset.metadata_json.get("manifest") or {})
        if not manifest:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_RENDER_PREP_MANIFEST, "Render-prep manifest payload is missing")

        cleaned = self._current_asset(source_video_id, MediaAssetType.CLEANED_VIDEO)
        source_video_asset = cleaned or self._current_asset(source_video_id, MediaAssetType.SOURCE_VIDEO_RAW)
        if source_video_asset is None:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_SOURCE_VIDEO_ASSET, "Current source video asset is missing")

        warnings = list(manifest.get("warnings") or [])
        contract = dict(manifest.get("render_contract") or {})
        if cleaned is not None:
            contract["source_video_asset_type"] = "CLEANED_VIDEO"
            if "using_cleaned_video" not in warnings:
                warnings.append("using_cleaned_video")
        else:
            contract["source_video_asset_type"] = "SOURCE_VIDEO_RAW"
            if "no_cleaned_video_fallback_raw" not in warnings:
                warnings.append("no_cleaned_video_fallback_raw")
        manifest["render_contract"] = contract
        manifest["warnings"] = warnings

        narration_key = _first_storage_key(manifest, "joined_narration")
        subtitle_key = _first_storage_key(manifest, "subtitle_srt") or _first_storage_key(manifest, "subtitle_json")
        if narration_key is None:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_NARRATION_ASSET, "Joined narration asset is missing in manifest")
        if subtitle_key is None:
            raise RenderPipelineError(RenderPipelineErrorCode.MISSING_SUBTITLE_ASSET, "Subtitle JSON asset is missing in manifest")

        for code, key in [
            (RenderPipelineErrorCode.MISSING_SOURCE_VIDEO_ASSET, source_video_asset.storage_key),
            (RenderPipelineErrorCode.MISSING_NARRATION_ASSET, narration_key),
            (RenderPipelineErrorCode.MISSING_SUBTITLE_ASSET, subtitle_key),
        ]:
            if not self.storage.exists(key):
                raise RenderPipelineError(code, f"Storage object missing: {key}")

        return ResolvedRenderInput(
            source_video_id=source_video_id,
            render_prep_manifest=manifest,
            source_video_storage_key=source_video_asset.storage_key,
            narration_storage_key=narration_key,
            subtitle_storage_key=subtitle_key,
            render_prep_manifest_asset_id=manifest_asset.id,
        )

    def _current_asset(self, source_video_id: UUID, asset_type: MediaAssetType) -> MediaAsset | None:
        return self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type == asset_type,
                MediaAsset.status == MediaAssetStatus.AVAILABLE,
                MediaAsset.is_current.is_(True),
            )
        )


def _first_storage_key(manifest: dict, output_key: str) -> str | None:
    values = ((manifest.get("current_outputs") or {}).get(output_key) or [])
    if not values:
        return None
    value = values[0]
    return value.get("storage_key") if isinstance(value, dict) else None
