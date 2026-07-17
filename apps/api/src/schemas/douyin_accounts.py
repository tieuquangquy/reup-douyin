from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.enums import (
    DouyinAccountConnectionStatus,
    DouyinAccountHealthStatus,
    DouyinAccountWarningLevel,
    DouyinBrowserConnectSessionStatus,
)


class DouyinAccountCreateRequest(BaseModel):
    workspace_id: UUID | None = None
    display_name: str = Field(min_length=1, max_length=180)
    session_cookie: str = Field(min_length=1)
    user_agent: str | None = None
    proxy_url: str | None = None
    headers_json: dict | None = None
    is_default: bool = False
    metadata_json: dict | None = None
    notes: str | None = None


class DouyinAccountUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=180)
    session_cookie: str | None = Field(default=None, min_length=1)
    user_agent: str | None = None
    proxy_url: str | None = None
    headers_json: dict | None = None
    status: DouyinAccountConnectionStatus | None = None
    is_default: bool | None = None
    metadata_json: dict | None = None
    notes: str | None = None


class DouyinAccountValidateRequest(BaseModel):
    validation_url: str | None = None


class DouyinManualImportPreflightSummary(BaseModel):
    code: str
    outcome: str
    summary: str
    next_action: str
    fetch_usable: bool
    source_type: str = "manual_import"
    detected_format: str | None = None
    cookie_strength: str | None = None
    checked_at: datetime | None = None


class DouyinBrowserHealthAlignmentSummary(BaseModel):
    interactive_browser_state: str
    automated_browser_validation_state: str
    detached_http_state: str
    effective_validation_path: str
    expected_intake_path: str
    validation_intake_aligned: bool
    stale_blocked_state_cleared: bool = False
    browser_evidence_strength: str
    operator_summary: str
    operator_detail: str | None = None
    last_browser_validation_status: str | None = None
    last_browser_validation_reason: str | None = None
    last_browser_validation_at: datetime | None = None
    runtime_attach_status: str | None = None
    page_recovery_status: str | None = None
    managed_runtime_status: str | None = None
    profile_conflict_status: str | None = None
    auto_reopen_attempted: bool = False
    auto_reopen_succeeded: bool = False
    auto_reopen_status: str | None = None
    runtime_reattached: bool = False
    validation_continued_after_reopen: bool = False
    final_validation_category: str | None = None
    validation_attempt_id: str | None = None
    challenge_category: str | None = None
    recommended_next_action: str | None = None
    challenge_state: str | None = None
    challenge_detected: bool = False
    challenge_count: int = 0
    profile_quarantine_state: str = "active_preferred"
    profile_quarantine_reason: str | None = None
    profile_quarantine_detected: bool = False
    profile_quarantine_recommended_next_action: str | None = None
    profile_quarantine_blocks_primary_flow: bool = False
    profile_quarantine_replaced_by_account_id: UUID | None = None
    profile_quarantine_clean_profile_recommendation: str | None = None
    challenge_last_detected_at: datetime | None = None
    challenge_last_solved_at: datetime | None = None
    challenge_cooldown_until: datetime | None = None
    challenge_repeat_limit_reached: bool = False
    challenge_recheck_attempt_id: str | None = None
    challenge_recheck_started_at: datetime | None = None
    challenge_recheck_resolved: bool = False
    challenge_same_runtime_reused: bool = False
    mark_challenge_solved_attempted: bool = False
    post_challenge_recheck_result: str | None = None
    same_profile_reused: bool = False
    runtime_reopened_for_recheck: bool = False
    intake_ready_after_recheck: bool = False


class DouyinAccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    display_name: str
    douyin_user_id: str | None
    status: DouyinAccountConnectionStatus
    is_default: bool
    session_cookie_present: bool
    session_cookie_preview: str | None
    user_agent: str | None
    proxy_url: str | None
    headers_json: dict | None
    health_status: DouyinAccountHealthStatus
    warning_level: DouyinAccountWarningLevel
    last_validated_at: datetime | None
    last_successful_validation_at: datetime | None
    last_validation_status: str | None
    validation_source: str | None
    next_validation_due_at: datetime | None
    expires_at: datetime | None
    last_error_code: str | None
    last_error_message: str | None
    account_health_label: str
    can_use_for_live_fetch: bool
    warning_summary_json: dict | None
    browser_context_available: bool = False
    browser_context_status: str | None = None
    browser_context_id: str | None = None
    browser_context_last_used_at: datetime | None = None
    manual_import_preflight: DouyinManualImportPreflightSummary | None = None
    browser_health_alignment: DouyinBrowserHealthAlignmentSummary
    metadata_json: dict | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DouyinAccountListResponse(BaseModel):
    accounts: list[DouyinAccountResponse]


class DouyinAccountValidationResponse(BaseModel):
    account: DouyinAccountResponse
    valid: bool
    status: DouyinAccountConnectionStatus
    reason: str
    douyin_user_id: str | None = None


class DouyinAccountChallengeActionResponse(BaseModel):
    account: DouyinAccountResponse
    action: str
    challenge_state: str | None = None
    challenge_category: str | None = None
    recommended_next_action: str | None = None
    valid: bool | None = None
    reason: str | None = None
    post_challenge_recheck_result: str | None = None
    same_profile_reused: bool | None = None
    same_runtime_reused: bool | None = None
    runtime_reopened_for_recheck: bool | None = None
    intake_ready_after_recheck: bool | None = None


class DouyinCurrentPageCaptureRequest(BaseModel):
    workspace_id: UUID | None = None
    preset_name: str | None = None
    filter_config: dict | None = None
    persist: bool = True
    max_videos: int = Field(default=50, ge=1, le=200)

    @model_validator(mode="after")
    def validate_thresholds(self) -> "DouyinCurrentPageCaptureRequest":
        if self.filter_config is None:
            return self
        min_duration = self.filter_config.get("min_duration_seconds")
        max_duration = self.filter_config.get("max_duration_seconds")
        if min_duration is not None and max_duration is not None and min_duration > max_duration:
            raise ValueError("min_duration_seconds cannot be greater than max_duration_seconds")
        return self


class DouyinCurrentPageDetectionResponse(BaseModel):
    diagnostics_id: str
    account_connection_id: UUID
    detected_page_type: str
    supported_capture: bool
    recommended_action: str
    recommended_action_label: str
    operator_message: str
    page_url: str | None = None
    normalized_profile_url: str | None = None
    title: str | None = None
    video_link_count: int = 0
    runtime_context_id: str | None = None
    runtime_attach_status: str | None = None
    page_recovery_status: str | None = None
    managed_runtime_status: str | None = None
    detected_at: datetime
    reason: str | None = None


class DouyinCurrentPageCaptureResponse(BaseModel):
    success: bool = True
    diagnostics_id: str
    account_connection_id: UUID
    detected_page_type: str
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
    fetch_mode: str = "operator_current_page_capture"
    used_existing_profile: bool = False
    douyin_account_connection_id: UUID
    selected_douyin_account_connection_id: UUID
    resolved_douyin_account_connection_id: UUID
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
    videos_normalized_count: int = 0
    videos_persisted_count: int = 0
    next_suggested_route: str = "/review-board?fresh=1"
    warning: str | None = None
    discovered_at: datetime
    current_page_url: str | None = None
    current_page_title: str | None = None
    current_page_video_link_count: int = 0


class DouyinAccountRevalidateRequest(BaseModel):
    workspace_id: UUID | None = None
    due_only: bool = True


class DouyinAccountRevalidateResponse(BaseModel):
    accounts_checked: int
    accounts_updated: int
    accounts: list[DouyinAccountResponse]


class DouyinAccountRevalidateJobResponse(BaseModel):
    job_id: UUID
    job_type: str
    queued_accounts_count: int | None = None


class DouyinAccountDeleteResponse(BaseModel):
    deleted_account_id: UUID
    delete_mode: str
    success: bool
    warnings: list[str] = Field(default_factory=list)
    recommended_follow_up: str | None = None


class DouyinProfileCleanupRequest(BaseModel):
    dry_run: bool = True
    apply: bool = False


class DouyinProfileCleanupProfileSummary(BaseModel):
    profile_id: str
    path_leaf: str
    classification: str
    linked_account_id: UUID | None = None
    active: bool = False
    planned_action: str
    reason: str | None = None
    quarantine_leaf: str | None = None
    last_modified_at: datetime | None = None


class DouyinProfileCleanupAccountSummary(BaseModel):
    account_id: UUID
    status: DouyinAccountConnectionStatus
    canonical_profile_id: str | None = None
    canonical_profile_path_leaf: str | None = None
    mapping_action: str
    reason: str | None = None


class DouyinProfileCleanupResponse(BaseModel):
    dry_run: bool
    applied: bool
    profiles_root_leaf: str
    quarantine_root_leaf: str | None = None
    profiles_scanned: int
    accounts_scanned: int
    canonical_count: int
    orphan_count: int
    duplicate_count: int
    quarantine_count: int
    skipped_active_count: int
    metadata_repairs_count: int
    profiles: list[DouyinProfileCleanupProfileSummary]
    accounts: list[DouyinProfileCleanupAccountSummary]


class DouyinBrowserConnectStartRequest(BaseModel):
    workspace_id: UUID | None = None
    account_connection_id: UUID | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=180)
    user_agent: str | None = None
    proxy_url: str | None = None
    is_default: bool = False
    timeout_seconds: int = Field(default=180, ge=30, le=900)


class DouyinBrowserConnectResetRequest(BaseModel):
    workspace_id: UUID | None = None


class DouyinBrowserConnectSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    status: DouyinBrowserConnectSessionStatus
    mode: str
    display_name: str | None
    started_at: datetime | None
    finished_at: datetime | None
    last_error: str | None
    error_code: str | None = None
    error_message: str | None = None
    outcome: str = "running"
    phase: str = "starting_browser"
    phase_deadline_at: datetime | None = None
    remaining_seconds: int | None = None
    timed_out_at: datetime | None = None
    age_seconds: int | None = None
    is_stale: bool = False
    stale_reason: str | None = None
    can_retry: bool = False
    can_cancel: bool = False
    can_resume: bool = False
    can_force_restart: bool = False
    can_resume_browser_session: bool = False
    can_retry_validation: bool = False
    should_keep_browser_open: bool = False
    validation_attempt_count: int = 0
    next_action: str | None = None
    runtime_available: bool | None = None
    manual_fallback_available: bool = True
    derived_account_id: UUID | None
    account: DouyinAccountResponse | None = None
    instructions: str
    login_url: str


class DouyinBrowserConnectActiveSessionResponse(BaseModel):
    session: DouyinBrowserConnectSessionResponse | None = None


class DouyinBrowserConnectResetResponse(BaseModel):
    reset_count: int
    affected_session_ids: list[UUID]
    resulting_state: DouyinBrowserConnectSessionStatus
    can_start_new: bool
    warning: str | None = None
