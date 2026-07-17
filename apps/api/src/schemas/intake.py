from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from src.enums import SourcePlatformEnum
from src.schemas.candidates import FilterConfigRequest


class IntakeDiscoverRequest(BaseModel):
    workspace_id: UUID | None = None
    profile_url: str
    source_platform: SourcePlatformEnum = SourcePlatformEnum.DOUYIN
    preset_name: str | None = None
    filter_config: FilterConfigRequest | None = None
    persist: bool = True
    force_live_refresh: bool = False
    douyin_account_connection_id: UUID | None = None

    @model_validator(mode="after")
    def validate_thresholds(self) -> "IntakeDiscoverRequest":
        if self.filter_config is None:
            return self
        config = self.filter_config
        if config.min_views is not None and config.max_views is not None and config.min_views > config.max_views:
            raise ValueError("min_views must be less than or equal to max_views")
        if config.min_likes is not None and config.max_likes is not None and config.min_likes > config.max_likes:
            raise ValueError("min_likes must be less than or equal to max_likes")
        if config.min_comments is not None and config.max_comments is not None and config.min_comments > config.max_comments:
            raise ValueError("min_comments must be less than or equal to max_comments")
        if config.min_shares is not None and config.max_shares is not None and config.min_shares > config.max_shares:
            raise ValueError("min_shares must be less than or equal to max_shares")
        if (
            config.min_duration_seconds is not None
            and config.max_duration_seconds is not None
            and config.min_duration_seconds > config.max_duration_seconds
        ):
            raise ValueError("min_duration_seconds must be less than or equal to max_duration_seconds")
        if (
            config.min_engagement_rate is not None
            and config.max_engagement_rate is not None
            and config.min_engagement_rate > config.max_engagement_rate
        ):
            raise ValueError("min_engagement_rate must be less than or equal to max_engagement_rate")
        if config.start_date is not None and config.end_date is not None and config.start_date > config.end_date:
            raise ValueError("start_date must be before or equal to end_date")
        return self


class IntakeReadyCheckRequest(BaseModel):
    workspace_id: UUID | None = None
    profile_url: str | None = None
    douyin_account_connection_id: UUID | None = None


class IntakeReadyCheckResponse(BaseModel):
    diagnostics_id: str
    readiness_status: str
    safe_to_run_intake_now: bool
    selected_account_id: UUID | None = None
    selected_account_label: str | None = None
    resolved_account_id: UUID | None = None
    resolved_account_label: str | None = None
    account_selection_mode: str | None = None
    account_selection_reason: str | None = None
    account_fallback_notice: str | None = None
    account_health: str | None = None
    browser_profile_status: str | None = None
    browser_profile_available: bool = False
    browser_reopen_needed: bool = False
    browser_reopen_attempted: bool = False
    browser_reopen_result: str | None = None
    intended_fetch_path: str | None = None
    fallback_allowed: bool = False
    recommended_action: str
    recommended_action_label: str
    summary_message: str
    preflight_cached: bool = False
    watchdog_result: str | None = None
    watchdog_status: str | None = None
    watchdog_reason: str | None = None
    preflight_result: str | None = None
    fetch_readiness_category: str | None = None
    preflight_failure_code: str | None = None
    preflight_failure_message: str | None = None
    challenge_state: str | None = None
    challenge_category: str | None = None
    challenge_count: int | None = None
    challenge_cooldown_until: datetime | None = None
    challenge_recommended_next_action: str | None = None
    profile_quarantine_state: str = "active_preferred"
    profile_quarantine_reason: str | None = None
    profile_quarantine_detected: bool = False
    profile_quarantine_recommended_next_action: str | None = None
    profile_quarantine_blocks_primary_flow: bool = False
    profile_quarantine_replaced_by_account_id: UUID | None = None
    profile_quarantine_clean_profile_recommendation: str | None = None
    profile_url: str | None = None


class IntakeDiscoverResponse(BaseModel):
    success: bool = True
    diagnostics_id: str
    source_profile_id: UUID
    crawl_session_id: UUID | None
    submitted_profile_url: str
    normalized_profile_identifier: str | None
    videos_discovered_count: int = 0
    videos_created_count: int = 0
    videos_updated_count: int = 0
    candidates_total_count: int = 0
    candidates_matched_count: int = 0
    candidates_rejected_count: int = 0
    candidate_results_count: int = 0
    filters_applied_summary: dict = Field(default_factory=dict)
    unsupported_filters_ignored: list[str] = Field(default_factory=list)
    fetch_mode: str = "live_fetch"
    used_existing_profile: bool = False
    douyin_account_connection_id: UUID | None = None
    selected_douyin_account_connection_id: UUID | None = None
    resolved_douyin_account_connection_id: UUID | None = None
    douyin_account_selection_mode: str | None = None
    douyin_account_selection_reason: str | None = None
    douyin_account_fallback_notice: str | None = None
    fetch_stage: str | None = None
    fetch_stage_code: str | None = None
    fetch_stage_message: str | None = None
    parser_strategy: str | None = None
    fetch_execution_path: str | None = None
    fallback_from_execution_path: str | None = None
    strategy_policy: str | None = None
    primary_execution_path: str | None = None
    http_fallback_attempted: bool | None = None
    http_fallback_reason: str | None = None
    preflight_ran: bool = False
    preflight_result: str | None = None
    fetch_readiness_category: str | None = None
    selected_fetch_path: str | None = None
    browser_reopen_attempted: bool | None = None
    browser_reopen_result: str | None = None
    preflight_failure_code: str | None = None
    preflight_cached: bool | None = None
    watchdog_result: str | None = None
    watchdog_status: str | None = None
    watchdog_reason: str | None = None
    runtime_reconciled: bool | None = None
    videos_normalized_count: int = 0
    videos_persisted_count: int = 0
    next_suggested_route: str = "/review-board?fresh=1"
    warning: str | None = Field(default=None)
    discovered_at: datetime


class IntakeSavedPresetPayload(BaseModel):
    profile_url: str
    preset_name: str | None = None
    filter_config: FilterConfigRequest | None = None
    force_live_refresh: bool = False
    douyin_account_connection_id: UUID | None = None


class IntakeSavedPresetCreateRequest(IntakeSavedPresetPayload):
    workspace_id: UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    notes: str | None = None


class IntakeSavedPresetUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    profile_url: str | None = None
    preset_name: str | None = None
    filter_config: FilterConfigRequest | None = None
    force_live_refresh: bool | None = None
    douyin_account_connection_id: UUID | None = None
    notes: str | None = None


class IntakeSavedPresetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    profile_url: str
    preset_name: str | None
    filter_config: dict = Field(default_factory=dict)
    force_live_refresh: bool
    douyin_account_connection_id: UUID | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class IntakeSavedPresetListResponse(BaseModel):
    presets: list[IntakeSavedPresetResponse]


class IntakeRecentProfileResponse(BaseModel):
    source_profile_id: UUID
    profile_url: str
    normalized_profile_identifier: str | None = None
    display_name: str | None = None
    last_crawled_at: datetime | None = None


class IntakeLatestSuccessShortcutResponse(BaseModel):
    crawl_session_id: UUID
    source_profile_id: UUID | None = None
    submitted_profile_url: str | None = None
    normalized_profile_identifier: str | None = None
    finished_at: datetime | None = None
    videos_discovered_count: int = 0


class IntakeBootstrapResponse(BaseModel):
    workspace_id: UUID
    saved_presets: list[IntakeSavedPresetResponse]
    recent_profiles: list[IntakeRecentProfileResponse]
    latest_success_shortcuts: list[IntakeLatestSuccessShortcutResponse]


class IntakeRunSummaryResponse(BaseModel):
    crawl_session_id: UUID
    source_profile_id: UUID | None = None
    submitted_profile_url: str | None = None
    normalized_profile_identifier: str | None = None
    source_profile_display_name: str | None = None
    status: str
    fetch_mode: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_seconds: int | None = None
    videos_discovered_count: int = 0
    videos_created_count: int = 0
    videos_updated_count: int = 0
    candidates_total_count: int = 0
    candidates_matched_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    fetch_observability: dict = Field(default_factory=dict)


class IntakeRunListResponse(BaseModel):
    runs: list[IntakeRunSummaryResponse]


class IntakeTroubleshootingSummaryResponse(BaseModel):
    category: str
    severity: str
    why: str
    recommended_actions: list[str] = Field(default_factory=list)


class IntakeRunDetailResponse(IntakeRunSummaryResponse):
    troubleshooting: IntakeTroubleshootingSummaryResponse


class IntakeRunCompareResponse(BaseModel):
    left: IntakeRunSummaryResponse
    right: IntakeRunSummaryResponse
    status_changed: bool
    duration_seconds_delta: int | None = None
    videos_discovered_delta: int = 0
    videos_created_delta: int = 0
    videos_updated_delta: int = 0
    error_code_changed: bool
    left_error_code: str | None = None
    right_error_code: str | None = None
    left_candidates_total: int = 0
    right_candidates_total: int = 0
    candidates_total_delta: int = 0
    left_candidates_matched: int = 0
    right_candidates_matched: int = 0
    candidates_matched_delta: int = 0
