from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

RENDER_PIPELINE_VERSION = "RENDER_PIPELINE_V1"


@dataclass(frozen=True)
class RenderRequest:
    source_video_id: UUID
    render_mode: str = "final"
    force_refresh: bool = False


@dataclass(frozen=True)
class ResolvedRenderInput:
    source_video_id: UUID
    render_prep_manifest: dict
    source_video_storage_key: str
    narration_storage_key: str
    subtitle_storage_key: str
    render_prep_manifest_asset_id: UUID


@dataclass(frozen=True)
class VideoProbe:
    width: int | None
    height: int | None
    fps: float | None
    duration_seconds: float | None
    video_codec: str | None = None
    audio_codec: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class RenderProfile:
    output_format: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    keep_source_resolution: bool = True
    keep_source_fps: bool = True
    subtitle_burned: bool = True
    audio_strategy: str = "replace_with_vietnamese_narration"


@dataclass(frozen=True)
class ExportInput:
    source_video_path: str
    narration_path: str
    subtitle_path: str
    output_path: str
    profile: RenderProfile
    source_probe: VideoProbe


@dataclass(frozen=True)
class ExportResult:
    output_path: str
    log_text: str
    warnings: list[str]
    command: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RenderPipelineResult:
    render_output_id: UUID
    output_asset_id: UUID
    render_version: str
    manifest: dict
    warnings: list[str]
