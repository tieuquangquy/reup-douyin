from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import UUID

from src.enums import ExternalPublicationStatus, PublishAttemptStatus, PublishReconciliationStatus, PublishTargetPlatform


@dataclass(frozen=True)
class PlatformAccountConfig:
    platform_account_id: UUID
    platform: PublishTargetPlatform
    page_id: str
    display_name: str
    access_token: str
    graph_api_version: str = "v20.0"


@dataclass(frozen=True)
class PublishMediaInput:
    publish_draft_id: UUID
    render_output_id: UUID
    source_video_id: UUID
    video_path: Path
    title: str
    description: str


@dataclass(frozen=True)
class PublishRequest:
    account: PlatformAccountConfig
    media: PublishMediaInput
    request_metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PublishResult:
    status: PublishAttemptStatus
    external_publish_id: str | None = None
    external_media_id: str | None = None
    external_reel_id: str | None = None
    external_permalink: str | None = None
    external_status: ExternalPublicationStatus = ExternalPublicationStatus.UNKNOWN
    response_summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reconciliation_required: bool = False
    reconciliation_status: PublishReconciliationStatus = PublishReconciliationStatus.NOT_REQUIRED
    reconciliation_note: str | None = None


@dataclass(frozen=True)
class PublishStatusSyncResult:
    external_status: ExternalPublicationStatus
    external_publish_id: str | None = None
    external_media_id: str | None = None
    external_reel_id: str | None = None
    external_permalink: str | None = None
    published_at: str | None = None
    response_summary: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    reconciliation_note: str | None = None


@dataclass(frozen=True)
class PublishRefreshOutcome:
    attempt_status: PublishAttemptStatus
    external_status: ExternalPublicationStatus
    reconciliation_status: PublishReconciliationStatus
    reconciliation_required: bool
    canonical_changed: bool = False
    note: str | None = None
    checked_at: datetime | None = None


@dataclass(frozen=True)
class PublishGateResult:
    allowed: bool
    reasons: list[str]
    warnings: list[str]

