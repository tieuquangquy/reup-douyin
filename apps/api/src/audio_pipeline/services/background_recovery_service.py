"""Recover Demucs stems without rerunning ASR or invalidating transcript authority."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.audio_pipeline.providers import DemucsSourceSeparationProvider
from src.core.settings import get_settings
from src.enums import MediaAssetStatus, MediaAssetType
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.storage.base import StorageBackend
from src.storage.local import LocalStorageBackend


class BackgroundRecoveryError(RuntimeError):
    pass


@dataclass(frozen=True)
class BackgroundRecoveryResult:
    source_video_id: str
    source_asset_id: str
    provider: str
    model: str
    cache_hit: bool
    vocal_asset_id: str
    background_asset_id: str
    vocal_storage_key: str
    background_storage_key: str
    vocal_sha256: str
    background_sha256: str
    background_size_bytes: int

    def to_dict(self) -> dict:
        return asdict(self)


class BackgroundRecoveryService:
    """Persist a successful two-stem retry while preserving DialogueBeat rows."""

    def __init__(
        self,
        db: Session,
        *,
        storage: StorageBackend | None = None,
        separation_provider: DemucsSourceSeparationProvider | None = None,
    ):
        self.db = db
        self.storage = storage or LocalStorageBackend(get_settings().local_storage_root)
        self.separation_provider = separation_provider or DemucsSourceSeparationProvider(
            storage=self.storage
        )

    def recover(self, source_video_id: UUID) -> BackgroundRecoveryResult:
        source_video = self.db.get(SourceVideo, source_video_id)
        if source_video is None:
            raise BackgroundRecoveryError("Source video not found")
        source_asset = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.source_video_id == source_video_id,
                MediaAsset.asset_type.in_(
                    [MediaAssetType.SOURCE_VIDEO_RAW, MediaAssetType.SOURCE_VIDEO]
                ),
                MediaAsset.status == MediaAssetStatus.AVAILABLE,
                MediaAsset.is_current.is_(True),
            )
        )
        if source_asset is None or not self.storage.exists(source_asset.storage_key):
            raise BackgroundRecoveryError("Current source video asset is missing")

        separation = self.separation_provider.separate(source_asset.storage_key)
        metadata = dict(separation.metadata or {})
        vocal_key = str(metadata.get("vocal_storage_key") or "").strip()
        background_key = str(metadata.get("background_storage_key") or "").strip()
        if separation.fallback_used or not vocal_key or not background_key:
            detail = str(metadata.get("error") or "Demucs returned fallback output")
            raise BackgroundRecoveryError(detail[:500])
        vocal_meta = self.storage.metadata(vocal_key)
        background_meta = self.storage.metadata(background_key)
        if (
            not vocal_meta.exists
            or not vocal_meta.checksum_sha256
            or not background_meta.exists
            or not background_meta.checksum_sha256
            or not background_meta.size_bytes
        ):
            raise BackgroundRecoveryError("Recovered Demucs stem metadata is incomplete")

        recovered_at = datetime.now(timezone.utc).isoformat()
        try:
            vocal_asset = self._upsert_stem_asset(
                source_video,
                source_asset=source_asset,
                asset_type=MediaAssetType.AUDIO_VOCAL_STEM,
                storage_key=vocal_key,
                checksum_sha256=vocal_meta.checksum_sha256,
                size_bytes=int(vocal_meta.size_bytes or 0),
                relative_path=vocal_meta.relative_path,
                role="demucs_vocals",
                recovered_at=recovered_at,
            )
            background_asset = self._upsert_stem_asset(
                source_video,
                source_asset=source_asset,
                asset_type=MediaAssetType.AUDIO_BACKGROUND_STEM,
                storage_key=background_key,
                checksum_sha256=background_meta.checksum_sha256,
                size_bytes=int(background_meta.size_bytes or 0),
                relative_path=background_meta.relative_path,
                role="demucs_no_vocals",
                recovered_at=recovered_at,
            )
            source_metadata = dict(source_video.metadata_json or {})
            previous = dict(source_metadata.get("separation") or {})
            source_metadata["separation"] = {
                "provider": self.separation_provider.provider_name,
                "fallback_used": False,
                "difficulty_flags": [],
                "metadata": {
                    **metadata,
                    "vocal_storage_key": vocal_key,
                    "background_storage_key": background_key,
                    "vocal_asset_id": str(vocal_asset.id),
                    "background_asset_id": str(background_asset.id),
                    "recovered_at": recovered_at,
                    "recovered_without_asr_rerun": True,
                    "previous_fallback_used": bool(previous.get("fallback_used")),
                },
            }
            source_video.metadata_json = source_metadata
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        return BackgroundRecoveryResult(
            source_video_id=str(source_video.id),
            source_asset_id=str(source_asset.id),
            provider=self.separation_provider.provider_name,
            model=str(metadata.get("model") or self.separation_provider.model_name),
            cache_hit=bool(metadata.get("cache_hit")),
            vocal_asset_id=str(vocal_asset.id),
            background_asset_id=str(background_asset.id),
            vocal_storage_key=vocal_key,
            background_storage_key=background_key,
            vocal_sha256=str(vocal_meta.checksum_sha256),
            background_sha256=str(background_meta.checksum_sha256),
            background_size_bytes=int(background_meta.size_bytes or 0),
        )

    def _upsert_stem_asset(
        self,
        source_video: SourceVideo,
        *,
        source_asset: MediaAsset,
        asset_type: MediaAssetType,
        storage_key: str,
        checksum_sha256: str,
        size_bytes: int,
        relative_path: str | None,
        role: str,
        recovered_at: str,
    ) -> MediaAsset:
        existing = self.db.scalar(
            select(MediaAsset).where(
                MediaAsset.workspace_id == source_video.workspace_id,
                MediaAsset.storage_key == storage_key,
            )
        )
        metadata = {
            "provider": self.separation_provider.provider_name,
            "model": self.separation_provider.model_name,
            "role": role,
            "source_asset_id": str(source_asset.id),
            "source_asset_sha256": source_asset.checksum_sha256,
            "recovered_at": recovered_at,
            "recovered_without_asr_rerun": True,
        }
        if existing is not None:
            if existing.source_video_id != source_video.id:
                raise BackgroundRecoveryError("Recovered stem storage key belongs to another video")
            existing.asset_type = asset_type
            existing.status = MediaAssetStatus.AVAILABLE
            existing.is_current = True
            existing.mime_type = "audio/wav"
            existing.size_bytes = size_bytes
            existing.checksum_sha256 = checksum_sha256
            existing.metadata_json = {**(existing.metadata_json or {}), **metadata}
            return existing

        previous_current = list(
            self.db.scalars(
                select(MediaAsset).where(
                    MediaAsset.source_video_id == source_video.id,
                    MediaAsset.asset_type == asset_type,
                    MediaAsset.is_current.is_(True),
                )
            )
        )
        for item in previous_current:
            item.is_current = False
        max_version = self.db.scalar(
            select(func.max(MediaAsset.version)).where(
                MediaAsset.source_video_id == source_video.id,
                MediaAsset.asset_type == asset_type,
            )
        )
        asset = MediaAsset(
            workspace_id=source_video.workspace_id,
            source_video_id=source_video.id,
            asset_type=asset_type,
            status=MediaAssetStatus.AVAILABLE,
            version=int(max_version or 0) + 1,
            storage_provider=self.storage.provider_name,
            storage_key=storage_key,
            logical_key=storage_key,
            relative_path=relative_path,
            manifest_group="audio_separation",
            is_current=True,
            mime_type="audio/wav",
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            metadata_json=metadata,
        )
        self.db.add(asset)
        self.db.flush()
        return asset
