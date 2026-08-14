from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from src.enums import JobStatus, MediaAssetStatus, MediaAssetType


class DownloadCreateRequest(BaseModel):
    source_video_id: UUID | None = None
    candidate_id: UUID | None = None
    force_refresh: bool = False
    account_connection_id: UUID | None = None
    expected_stage_version: str | None = None

    @model_validator(mode="after")
    def require_one_canonical_selector(self) -> "DownloadCreateRequest":
        if (self.source_video_id is None) == (self.candidate_id is None):
            raise ValueError("Exactly one of source_video_id or candidate_id is required")
        return self


class DownloadCreateResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    source_video_id: UUID
    asset_count: int
    manifest: dict
    runtime_version: str


class MediaAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_video_id: UUID
    asset_type: MediaAssetType
    status: MediaAssetStatus
    version: int
    storage_provider: str
    storage_key: str
    logical_key: str | None
    relative_path: str | None
    manifest_group: str | None
    is_current: bool
    created_by_job_id: UUID | None
    source_url: str | None
    mime_type: str | None
    size_bytes: int | None
    checksum_sha256: str | None
    metadata_json: dict | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


class SourceVideoAssetsResponse(BaseModel):
    source_video_id: UUID
    assets: list[MediaAssetResponse]
    manifest: dict


class LocalAssetRevealResponse(BaseModel):
    revealed: bool
    asset_type: str
    source_video_id: UUID
