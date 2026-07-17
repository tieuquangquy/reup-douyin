from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import (
    ExternalPublicationStatus,
    PlatformAccountStatus,
    PublishAttemptStatus,
    PublishDraftStatus,
    PublishReconciliationStatus,
    PublishTargetPlatform,
)


class HashtagDraftItem(BaseModel):
    tag: str = Field(min_length=1, max_length=80)
    source: str = "operator"


class PublishDraftCreateRequest(BaseModel):
    source_video_id: UUID | None = None
    render_output_id: UUID | None = None
    target_platform: PublishTargetPlatform
    platform_account_ref: str | None = None
    generation_mode: str = "deterministic_v1"


class PublishDraftUpdateRequest(BaseModel):
    target_platform: PublishTargetPlatform | None = None
    platform_account_ref: str | None = None
    title: str | None = None
    caption: str | None = None
    cta_text: str | None = None
    hashtags: list[HashtagDraftItem] | None = None
    language_code: str | None = None
    platform_notes: str | None = None
    scheduling_notes: str | None = None
    notes: str | None = None


class PublishDraftScheduleRequest(BaseModel):
    planned_publish_at: datetime
    timezone: str = "Asia/Bangkok"
    scheduling_notes: str | None = None


class PublishDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    source_video_id: UUID
    render_output_id: UUID | None
    target_platform: str
    platform_account_ref: str | None
    version: int
    status: PublishDraftStatus
    title: str | None
    caption: str | None
    cta_text: str | None
    language_code: str | None
    hashtags_json: list | None
    caption_draft_json: dict | None
    cta_draft_json: dict | None
    schedule_json: dict | None
    planned_publish_at: datetime | None
    timezone: str | None
    scheduled_at: datetime | None
    ready_at: datetime | None
    generation_source: str | None
    platform_payload_json: dict | None
    metadata_json: dict | None
    platform_notes: str | None
    scheduling_notes: str | None
    notes: str | None
    error_message: str | None
    canonical_publish_attempt_id: UUID | None
    latest_publish_attempt_id: UUID | None
    current_publication_status: ExternalPublicationStatus | None
    current_external_publish_id: str | None
    current_external_permalink: str | None
    published_at: datetime | None
    last_publish_synced_at: datetime | None
    publication_summary_json: dict | None
    assigned_platform_account_id: UUID | None
    assignment_status: str | None
    assigned_at: datetime | None
    assigned_reason: str | None
    assigned_by: str | None
    assignment_metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class PublishDraftListResponse(BaseModel):
    drafts: list[PublishDraftResponse]


class PublishTargetResponse(BaseModel):
    platform: PublishTargetPlatform
    label: str
    caption_max_length: int
    hashtag_limit: int
    supports_scheduling: bool
    account_ref_required: bool = False


class PlatformAccountCreateRequest(BaseModel):
    workspace_id: UUID | None = None
    platform: PublishTargetPlatform = PublishTargetPlatform.FACEBOOK_REELS
    display_name: str = Field(min_length=1, max_length=180)
    external_account_id: str = Field(min_length=1, max_length=180)
    token_reference: str | None = Field(default="FACEBOOK_PAGE_ACCESS_TOKEN", max_length=240)
    status: PlatformAccountStatus = PlatformAccountStatus.ACTIVE
    priority: int = Field(default=100, ge=0, le=1000)
    is_on_hold: bool = False
    hold_reason: str | None = None
    cooldown_until: datetime | None = None
    allowed_niches_json: list | None = None
    metadata_json: dict | None = None
    routing_notes: str | None = None
    notes: str | None = None


class PlatformAccountUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=180)
    external_account_id: str | None = Field(default=None, min_length=1, max_length=180)
    token_reference: str | None = Field(default=None, max_length=240)
    status: PlatformAccountStatus | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    is_on_hold: bool | None = None
    hold_reason: str | None = None
    cooldown_until: datetime | None = None
    allowed_niches_json: list | None = None
    metadata_json: dict | None = None
    routing_notes: str | None = None
    notes: str | None = None


class PlatformAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    platform: PublishTargetPlatform
    display_name: str
    external_account_id: str
    token_reference: str | None
    status: PlatformAccountStatus
    priority: int
    is_on_hold: bool
    hold_reason: str | None
    cooldown_until: datetime | None
    allowed_niches_json: list | None
    metadata_json: dict | None
    routing_notes: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PlatformAccountListResponse(BaseModel):
    accounts: list[PlatformAccountResponse]


class PublishDraftPublishRequest(BaseModel):
    platform_account_id: UUID
    publish_mode: str = "publish_now"


class PublishAttemptResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    publish_draft_id: UUID
    platform: PublishTargetPlatform
    platform_account_id: UUID
    attempt_number: int
    status: PublishAttemptStatus
    started_at: datetime | None
    finished_at: datetime | None
    external_publish_id: str | None
    external_media_id: str | None
    external_reel_id: str | None
    external_permalink: str | None
    external_status: ExternalPublicationStatus | None
    reconciliation_status: PublishReconciliationStatus | None
    reconciliation_required: bool
    last_status_checked_at: datetime | None
    last_status_sync_result_json: dict | None
    request_summary_json: dict | None
    response_summary_json: dict | None
    warning_summary_json: dict | None
    error_code: str | None
    error_message: str | None
    created_by_job_id: UUID | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class PublishAttemptListResponse(BaseModel):
    attempts: list[PublishAttemptResponse]


class PublishStatusResponse(BaseModel):
    publish_draft_id: UUID
    status: PublishDraftStatus | None = None
    latest_attempt: PublishAttemptResponse | None
    canonical_attempt: PublishAttemptResponse | None = None
    is_published: bool
    current_publication_status: ExternalPublicationStatus | None = None
    current_external_publish_id: str | None = None
    current_external_permalink: str | None = None
    published_at: datetime | None = None
    last_publish_synced_at: datetime | None = None
    publication_summary_json: dict | None = None


class PublicationSummaryResponse(BaseModel):
    publish_draft_id: UUID
    draft_status: PublishDraftStatus
    current_publication_status: ExternalPublicationStatus
    canonical_publish_attempt_id: UUID | None = None
    latest_publish_attempt_id: UUID | None = None
    current_external_publish_id: str | None = None
    current_external_permalink: str | None = None
    published_at: datetime | None = None
    last_publish_synced_at: datetime | None = None
    attempt_count: int
    active_attempt_count: int
    needs_reconciliation_count: int
    duplicate_success_count: int
    requires_operator_attention: bool
    warnings: list[str]


class PublishHistoryResponse(BaseModel):
    publish_draft_id: UUID
    summary: PublicationSummaryResponse
    attempts: list[PublishAttemptResponse]
    canonical_attempt: PublishAttemptResponse | None = None
    latest_attempt: PublishAttemptResponse | None = None


class PublishReconcileResponse(BaseModel):
    publish_draft_id: UUID
    refreshed_attempt_ids: list[UUID]
    stale_attempt_ids: list[UUID]
    errors: list[dict]
    summary: PublicationSummaryResponse
