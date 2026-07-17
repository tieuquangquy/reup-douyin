from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from src.enums import SourcePlatformEnum


@dataclass(frozen=True)
class NormalizedProfileIdentity:
    source_platform: SourcePlatformEnum
    source_profile_external_id: str
    canonical_url: str
    handle: str | None = None


@dataclass(frozen=True)
class NormalizedSourceProfile:
    source_platform: SourcePlatformEnum
    source_profile_external_id: str
    profile_url: str
    display_name: str | None = None
    handle: str | None = None
    metadata_json: dict | None = None
    raw_payload_json: dict | None = None


@dataclass(frozen=True)
class NormalizedMetricSnapshot:
    view_count: int | None = None
    like_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    favorite_count: int | None = None
    raw_payload_json: dict | None = None


@dataclass(frozen=True)
class NormalizedSourceVideo:
    source_platform: SourcePlatformEnum
    source_profile_external_id: str
    source_video_external_id: str
    source_video_url: str
    author_display_name: str | None = None
    title: str | None = None
    description: str | None = None
    duration_seconds: float | None = None
    posted_at: datetime | None = None
    hashtags: list[str] = field(default_factory=list)
    thumbnail_url: str | None = None
    raw_visibility: str | None = None
    raw_status: str | None = None
    metadata_json: dict | None = None
    raw_payload_json: dict | None = None
    metrics: NormalizedMetricSnapshot = field(default_factory=NormalizedMetricSnapshot)


@dataclass(frozen=True)
class SourceFetchResult:
    profile: NormalizedSourceProfile
    videos: list[NormalizedSourceVideo]
    raw_payload_json: dict | None = None
    metadata_json: dict | None = None


@dataclass(frozen=True)
class IngestSummary:
    crawl_session_id: str
    status: str
    source_profile_id: str | None
    source_platform: str
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    videos_discovered_count: int
    videos_created_count: int
    videos_updated_count: int
    snapshots_created_count: int
    error_code: str | None = None
    error_message: str | None = None

