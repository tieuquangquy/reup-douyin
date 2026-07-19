from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from src.enums import JobStatus, RenderOutputStatus


class RenderCreateRequest(BaseModel):
    source_video_id: UUID
    render_mode: str = "final"
    force_refresh: bool = False


class RenderCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    source_video_id: UUID


class RenderOutputResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_video_id: UUID
    media_asset_id: UUID | None
    status: RenderOutputStatus
    target_platform: str | None
    version: int
    render_type: str | None
    output_format: str | None
    width: int | None
    height: int | None
    fps: float | None
    duration_seconds: float | None
    video_codec: str | None
    audio_codec: str | None
    subtitle_burned: bool
    audio_strategy: str | None
    render_version: str | None
    created_by_job_id: UUID | None
    size_bytes: int | None = None
    warning_summary_json: dict | None
    render_settings_json: dict | None
    metadata_json: dict | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RenderListResponse(BaseModel):
    source_video_id: UUID
    renders: list[RenderOutputResponse]
