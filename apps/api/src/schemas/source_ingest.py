from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import CrawlSessionStatus, SourcePlatformEnum, SourceProfileStatus, SourceVideoStatus


class SourceProfileIngestRequest(BaseModel):
    workspace_id: UUID | None = None
    profile_url: str
    source_platform: SourcePlatformEnum = SourcePlatformEnum.DOUYIN
    niche_tag_ids: list[UUID] = Field(default_factory=list)
    crawl_mode: str | None = None
    adapter_payload_json: dict | None = Field(
        default=None,
        description="Dev/test payload for adapter normalization. Real fetch clients should replace this later.",
    )


class IngestSummaryResponse(BaseModel):
    crawl_session_id: UUID
    status: CrawlSessionStatus
    source_profile_id: UUID | None
    source_platform: SourcePlatformEnum
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    videos_discovered_count: int
    videos_created_count: int
    videos_updated_count: int
    snapshots_created_count: int
    error_code: str | None
    error_message: str | None


class SourceProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_platform: SourcePlatformEnum
    source_profile_external_id: str
    profile_url: str
    display_name: str | None
    handle: str | None
    status: SourceProfileStatus
    last_crawled_at: datetime | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class CrawlSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_platform: SourcePlatformEnum | None
    source_profile_id: UUID | None
    submitted_profile_url: str | None
    normalized_profile_identifier: str | None
    status: CrawlSessionStatus
    started_at: datetime | None
    finished_at: datetime | None
    videos_discovered_count: int
    videos_created_count: int
    videos_updated_count: int
    snapshots_created_count: int
    error_code: str | None
    error_message: str | None
    raw_summary_json: dict | None
    result_summary_json: dict | None
    created_at: datetime
    updated_at: datetime


class SourceVideoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_profile_id: UUID
    source_platform: SourcePlatformEnum
    source_video_external_id: str
    source_url: str
    caption: str | None
    posted_at: datetime | None
    duration_seconds: float | None
    status: SourceVideoStatus
    score: float | None
    language_code: str | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class CrawlSessionListResponse(BaseModel):
    crawl_sessions: list[CrawlSessionResponse]


class SourceProfileListResponse(BaseModel):
    source_profiles: list[SourceProfileResponse]


class SourceVideoListResponse(BaseModel):
    videos: list[SourceVideoResponse]

