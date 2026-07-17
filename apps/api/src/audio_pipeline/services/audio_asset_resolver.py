from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.audio_pipeline.errors import AudioAnalysisError, AudioAnalysisErrorCode
from src.audio_pipeline.services.asset_selection import choose_audio_input_asset
from src.audio_pipeline.types import ResolvedAudioInput
from src.enums import MediaAssetStatus
from src.models.ingestion import SourceVideo
from src.models.media import MediaAsset
from src.storage.base import StorageBackend


class AudioAssetResolver:
    def __init__(self, db: Session, storage: StorageBackend):
        self.db = db
        self.storage = storage

    def resolve(self, source_video_id: UUID) -> tuple[SourceVideo, ResolvedAudioInput]:
        source_video = self.db.get(SourceVideo, source_video_id)
        if source_video is None:
            raise AudioAnalysisError(AudioAnalysisErrorCode.MISSING_SOURCE_ASSET, "Source video not found")

        asset = choose_audio_input_asset(self._current_assets(source_video_id))
        if asset is None:
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.MISSING_SOURCE_ASSET,
                "No SOURCE_AUDIO_EXTRACT or SOURCE_VIDEO_RAW asset is available",
            )
        if not self.storage.exists(asset.storage_key):
            raise AudioAnalysisError(
                AudioAnalysisErrorCode.MISSING_SOURCE_ASSET,
                f"Asset file is missing from storage: {asset.storage_key}",
            )

        return source_video, ResolvedAudioInput(
            source_video_id=source_video.id,
            input_asset_id=asset.id,
            input_asset_type=asset.asset_type,
            storage_key=asset.storage_key,
            source_video_duration_seconds=source_video.duration_seconds,
            source_caption=source_video.caption,
        )

    def _current_assets(self, source_video_id: UUID) -> list[MediaAsset]:
        return list(
            self.db.scalars(
                select(MediaAsset).where(
                    MediaAsset.source_video_id == source_video_id,
                    MediaAsset.status == MediaAssetStatus.AVAILABLE,
                    MediaAsset.is_current.is_(True),
                )
            )
        )
