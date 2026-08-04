from __future__ import annotations

from datetime import datetime
from typing import Literal
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

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


class FacebookAccountSetupCheck(BaseModel):
    code: str
    passed: bool
    blocking: bool
    message: str


class FacebookAccountSetupCheckResponse(BaseModel):
    platform_account_id: UUID
    ready_for_publication_setup: bool
    network_used: bool = False
    token_value_exposed: bool = False
    checks: list[FacebookAccountSetupCheck]
    blocker_codes: list[str]


class FacebookPublishSafetyStatusResponse(BaseModel):
    platform_account_id: UUID
    state: Literal[
        "READY",
        "WARM_UP",
        "CADENCE_WAIT",
        "COOLDOWN",
        "HOLD",
        "RECONNECT_REQUIRED",
        "BLOCKED",
    ]
    eligible_for_publish: bool
    credential_source: str | None = None
    managed_credential: bool = False
    hold_reason: str | None = None
    cooldown_until: datetime | None = None
    connected_at: datetime | None = None
    capability_verified_at: datetime | None = None
    capability_expires_at: datetime | None = None
    warmup_until: datetime | None = None
    next_publish_at: datetime | None = None
    verified_publish_scopes: list[str]
    page_tasks: list[str]
    attempts_24h: int
    failures_24h: int
    active_attempts: int
    unresolved_attempts: int
    effective_min_interval_minutes: int
    effective_max_attempts_24h: int
    warmup_stage: Literal["PILOT", "OBSERVE", "STANDARD"]
    confirmed_connector_publishes: int
    next_stage_min_successes: int | None = None
    next_stage_earliest_at: datetime | None = None
    blocker_codes: list[str]
    blockers: list[str]
    warnings: list[str]


class FacebookOAuthConfigurationUpdateRequest(BaseModel):
    app_id: str = Field(min_length=5, max_length=240, pattern=r"^\d+$")
    app_secret: str | None = Field(default=None, min_length=8, max_length=1000)
    redirect_uri: str = Field(min_length=8, max_length=1000)
    graph_api_version: str = Field(pattern=r"^v\d+\.\d+$", max_length=40)
    requested_scopes: list[str] = Field(min_length=2, max_length=4)

    @field_validator("app_id", "app_secret", "redirect_uri", "graph_api_version", mode="before")
    @classmethod
    def strip_oauth_configuration_values(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("redirect_uri")
    @classmethod
    def validate_redirect_uri(cls, value: str) -> str:
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Redirect URI must be an absolute HTTP(S) URL")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Redirect URI cannot contain credentials, query, or fragment")
        if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1"}:
            raise ValueError("Non-local redirect URI must use HTTPS")
        return value

    @field_validator("requested_scopes")
    @classmethod
    def normalize_requested_scopes(cls, value: list[str]) -> list[str]:
        normalized = sorted({str(item).strip() for item in value if str(item).strip()})
        if len(normalized) != len(value):
            raise ValueError("Requested scopes must be unique and non-empty")
        return normalized


class FacebookOAuthConfigurationResponse(BaseModel):
    configured: bool
    missing_configuration: list[str]
    graph_api_version: str
    redirect_uri: str
    requested_scopes: list[str]
    encrypted_credential_store_ready: bool
    raw_token_entry_required: bool = False
    source: Literal["DATABASE", "ENVIRONMENT", "NONE"] = "NONE"
    app_id: str | None = None
    app_secret_configured: bool = False
    editable: bool = True
    updated_at: datetime | None = None


class FacebookOAuthStartResponse(BaseModel):
    connection_id: UUID
    authorization_url: str
    expires_at: datetime
    token_value_exposed: bool = False


class FacebookOAuthCallbackRequest(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=20, max_length=1000)


class FacebookOAuthPage(BaseModel):
    page_id: str
    display_name: str
    tasks: list[str]
    picture_url: str | None = None


class FacebookOAuthSessionResponse(BaseModel):
    connection_id: UUID
    status: Literal[
        "AUTHORIZATION_PENDING",
        "PAGE_SELECTION_REQUIRED",
        "COMPLETED",
        "FAILED",
        "EXPIRED",
    ]
    pages: list[FacebookOAuthPage]
    granted_scopes: list[str]
    expires_at: datetime
    error_code: str | None = None
    error_message: str | None = None
    token_value_exposed: bool = False


class FacebookOAuthConnectPageRequest(BaseModel):
    connection_id: UUID
    page_id: str = Field(min_length=1, max_length=180)
    priority: int = Field(default=100, ge=0, le=1000)


class FacebookOAuthConnectPageResponse(BaseModel):
    account: PlatformAccountResponse
    setup_check: FacebookAccountSetupCheckResponse
    created: bool
    token_value_exposed: bool = False


class ExistingFacebookReelRegisterRequest(BaseModel):
    publish_draft_id: UUID
    platform_account_id: UUID
    external_publish_id: str = Field(min_length=1, max_length=240)
    external_media_id: str | None = Field(default=None, min_length=1, max_length=240)
    external_reel_id: str | None = Field(default=None, min_length=1, max_length=240)
    external_permalink: str = Field(min_length=1, max_length=1000)
    published_at: datetime
    operator_attestation: Literal["EXISTING_FACEBOOK_REEL_VERIFIED"]

    @field_validator("published_at")
    @classmethod
    def published_at_must_have_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("published_at must include a timezone")
        return value

    @field_validator("external_permalink")
    @classmethod
    def permalink_must_be_facebook(cls, value: str) -> str:
        host = (urlparse(value.strip()).hostname or "").lower()
        if not (host == "fb.watch" or host == "facebook.com" or host.endswith(".facebook.com")):
            raise ValueError("external_permalink must belong to facebook.com or fb.watch")
        return value.strip()

    @model_validator(mode="after")
    def ensure_media_reference(self):
        if not (self.external_reel_id or self.external_media_id or self.external_publish_id):
            raise ValueError("At least one external Facebook media reference is required")
        return self


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


class PlatformPublicationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    publish_draft_id: UUID | None
    source_video_id: UUID | None
    render_output_id: UUID | None
    platform: PublishTargetPlatform
    platform_account_id: UUID
    publish_attempt_id: UUID | None
    external_publish_id: str
    external_media_id: str | None
    external_reel_id: str | None
    external_permalink: str | None
    status: ExternalPublicationStatus
    is_canonical: bool
    published_at: datetime | None
    last_synced_at: datetime | None
    content_fingerprint_sha256: str | None
    origin: Literal["CONNECTOR_PUBLISH", "MANUAL_IMPORT", "FACEBOOK_DISCOVERY"]
    native_product_placement_status: str
    affiliate_comment_status: str
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class PlatformPublicationListResponse(BaseModel):
    publications: list[PlatformPublicationResponse]
    total_count: int
    limit: int
    offset: int


class FacebookReelDiscoveryItem(BaseModel):
    reel_id: str
    description: str | None = None
    created_time: datetime | None = None
    permalink_url: str | None = None
    thumbnail_url: str | None = None
    already_imported: bool = False
    platform_publication_id: UUID | None = None


class FacebookReelDiscoveryResponse(BaseModel):
    platform_account_id: UUID
    items: list[FacebookReelDiscoveryItem]
    next_cursor: str | None = None
    network_used: bool = True


class FacebookReelDiscoveryImportRequest(BaseModel):
    platform_account_id: UUID
    reel_id: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=10000)
    created_time: datetime | None = None
    permalink_url: str | None = Field(default=None, max_length=1000)
    thumbnail_url: str | None = Field(default=None, max_length=2000)
    publish_draft_id: UUID | None = None

    @field_validator("created_time")
    @classmethod
    def discovery_time_must_have_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("created_time must include a timezone")
        return value

    @field_validator("permalink_url")
    @classmethod
    def discovery_permalink_must_be_facebook(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if cleaned.startswith("/") and not cleaned.startswith("//"):
            cleaned = f"https://www.facebook.com{cleaned}"
        host = (urlparse(cleaned).hostname or "").lower()
        if not (host == "facebook.com" or host.endswith(".facebook.com") or host == "fb.watch"):
            raise ValueError("permalink_url must belong to facebook.com or fb.watch")
        return cleaned


class PlatformPublicationLinkDraftRequest(BaseModel):
    publish_draft_id: UUID


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
