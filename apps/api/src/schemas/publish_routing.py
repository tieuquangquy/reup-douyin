from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.enums import (
    PlatformAccountHealthStatus,
    PlatformAccountStatus,
    PublishAccountAssignmentStatus,
    PublishDraftStatus,
    PublishRoutingRuleStatus,
    PublishTargetPlatform,
)


class AccountHealthSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform_account_id: UUID
    display_name: str
    platform: PublishTargetPlatform
    account_status: PlatformAccountStatus
    health_status: PlatformAccountHealthStatus
    priority: int
    is_on_hold: bool
    cooldown_until: datetime | None
    attempts_7d: int
    succeeded_7d: int
    failed_7d: int
    needs_reconciliation_count: int
    assigned_draft_count: int
    scheduled_draft_count: int
    recent_error_code: str | None
    success_rate_percent: float
    reasons: list[str]


class AccountEligibilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    platform_account_id: UUID
    display_name: str
    eligible: bool
    health_status: PlatformAccountHealthStatus
    score: int
    blocking_reasons: list[str]
    warnings: list[str]
    recommendation_reasons: list[str]


class RoutingRecommendationResponse(BaseModel):
    publish_draft_id: UUID
    matched_rule_ids: list[UUID]
    matched_rule_names: list[str]
    recommended_accounts: list[AccountEligibilityResponse]
    blocked_accounts: list[AccountEligibilityResponse]
    warnings: list[str]


class DraftAssignmentRequest(BaseModel):
    platform_account_id: UUID
    reason: str | None = None
    assigned_by: str = "local_operator"
    force_override: bool = False


class BulkAssignDraftsRequest(BaseModel):
    publish_draft_ids: list[UUID] = Field(min_length=1)
    platform_account_id: UUID
    reason: str | None = None
    assigned_by: str = "local_operator"
    force_override: bool = False


class PublishDraftQueueItem(BaseModel):
    publish_draft_id: UUID
    source_video_id: UUID
    title: str | None
    status: PublishDraftStatus
    target_platform: str
    planned_publish_at: datetime | None
    assigned_platform_account_id: UUID | None
    assignment_status: PublishAccountAssignmentStatus
    assigned_reason: str | None
    recommended_platform_account_id: UUID | None
    recommended_account_name: str | None
    recommendation_reasons: list[str]
    warnings: list[str]


class PublishControlQueueResponse(BaseModel):
    generated_at: datetime
    accounts: list[AccountHealthSummaryResponse]
    unassigned_drafts: list[PublishDraftQueueItem]
    assigned_drafts: list[PublishDraftQueueItem]
    scheduled_drafts: list[PublishDraftQueueItem]
    needs_attention: list[PublishDraftQueueItem]


class PublishRoutingRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    platform: PublishTargetPlatform
    rule_name: str
    status: PublishRoutingRuleStatus
    priority: int
    match_json: dict | None
    action_json: dict | None
    fallback_behavior: str | None
    metadata_json: dict | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class PublishRoutingRuleCreateRequest(BaseModel):
    workspace_id: UUID
    platform: PublishTargetPlatform = PublishTargetPlatform.FACEBOOK_REELS
    rule_name: str = Field(min_length=1, max_length=160)
    status: PublishRoutingRuleStatus = PublishRoutingRuleStatus.ACTIVE
    priority: int = Field(default=100, ge=0, le=1000)
    match_json: dict | None = None
    action_json: dict | None = None
    fallback_behavior: str | None = None
    metadata_json: dict | None = None
    notes: str | None = None


class PublishRoutingRuleUpdateRequest(BaseModel):
    rule_name: str | None = Field(default=None, min_length=1, max_length=160)
    status: PublishRoutingRuleStatus | None = None
    priority: int | None = Field(default=None, ge=0, le=1000)
    match_json: dict | None = None
    action_json: dict | None = None
    fallback_behavior: str | None = None
    metadata_json: dict | None = None
    notes: str | None = None


class PublishRoutingRuleListResponse(BaseModel):
    rules: list[PublishRoutingRuleResponse]
