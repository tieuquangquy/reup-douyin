from __future__ import annotations

from pathlib import Path

from src.render_pipeline.errors import RenderPipelineError, RenderPipelineErrorCode
from src.render_pipeline.types import VideoProbe
from src.storage.base import StorageBackend


class VideoProbeService:
    def __init__(self, storage: StorageBackend):
        self.storage = storage

    def probe(self, storage_key: str) -> VideoProbe:
        metadata = self.storage.metadata(storage_key)
        if not metadata.exists or not metadata.size_bytes:
            raise RenderPipelineError(RenderPipelineErrorCode.PROBE_FAILED, f"Cannot probe missing or empty asset: {storage_key}")
        suffix = Path(storage_key).suffix.lower().lstrip(".")
        return VideoProbe(
            width=None,
            height=None,
            fps=None,
            duration_seconds=None,
            video_codec=suffix or None,
            audio_codec=None,
            raw={
                "storage_key": storage_key,
                "size_bytes": metadata.size_bytes,
                "probe_strategy": "storage_metadata_fallback",
            },
        )
