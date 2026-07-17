export type DouyinAccountStatus = "ACTIVE" | "INVALID" | "EXPIRED" | "DISABLED" | "BLOCKED";
export type DouyinAccountHealthStatus = "HEALTHY" | "STALE" | "EXPIRING_SOON" | "INVALID" | "EXPIRED" | "BLOCKED" | "DISABLED" | "UNKNOWN";
export type DouyinAccountWarningLevel = "NONE" | "INFO" | "WARN" | "BLOCK";

export type DouyinManualImportPreflight = {
  code: string;
  outcome: string;
  summary: string;
  next_action: string;
  fetch_usable: boolean;
  source_type: string;
  detected_format: string | null;
  cookie_strength: string | null;
  checked_at: string | null;
};

export type DouyinBrowserHealthAlignment = {
  interactive_browser_state: string;
  automated_browser_validation_state: string;
  detached_http_state: string;
  effective_validation_path: string;
  expected_intake_path: string;
  validation_intake_aligned: boolean;
  stale_blocked_state_cleared: boolean;
  browser_evidence_strength: string;
  operator_summary: string;
  operator_detail: string | null;
  last_browser_validation_status: string | null;
  last_browser_validation_reason: string | null;
  last_browser_validation_at: string | null;
  runtime_attach_status: string | null;
  page_recovery_status: string | null;
  managed_runtime_status: string | null;
  profile_conflict_status: string | null;
  auto_reopen_attempted: boolean;
  auto_reopen_succeeded: boolean;
  auto_reopen_status: string | null;
  runtime_reattached: boolean;
  validation_continued_after_reopen: boolean;
  final_validation_category: string | null;
  validation_attempt_id: string | null;
  challenge_category: string | null;
  recommended_next_action: string | null;
  challenge_state: string | null;
  challenge_detected: boolean;
  challenge_count: number;
  challenge_last_detected_at: string | null;
  challenge_last_solved_at: string | null;
  challenge_cooldown_until: string | null;
  challenge_repeat_limit_reached: boolean;
  challenge_recheck_attempt_id: string | null;
  challenge_recheck_started_at: string | null;
  challenge_recheck_resolved: boolean;
  challenge_same_runtime_reused: boolean;
  mark_challenge_solved_attempted: boolean;
  post_challenge_recheck_result: string | null;
  same_profile_reused: boolean;
  runtime_reopened_for_recheck: boolean;
  intake_ready_after_recheck: boolean;
  profile_quarantine_state: string;
  profile_quarantine_reason: string | null;
  profile_quarantine_detected: boolean;
  profile_quarantine_recommended_next_action: string | null;
  profile_quarantine_blocks_primary_flow: boolean;
  profile_quarantine_replaced_by_account_id: string | null;
  profile_quarantine_clean_profile_recommendation: string | null;
};

export type DouyinAccount = {
  id: string;
  workspace_id: string;
  display_name: string;
  douyin_user_id: string | null;
  status: DouyinAccountStatus;
  is_default: boolean;
  session_cookie_present: boolean;
  session_cookie_preview: string | null;
  user_agent: string | null;
  proxy_url: string | null;
  headers_json: Record<string, unknown> | null;
  health_status: DouyinAccountHealthStatus;
  warning_level: DouyinAccountWarningLevel;
  last_validated_at: string | null;
  last_successful_validation_at: string | null;
  last_validation_status: string | null;
  validation_source: string | null;
  next_validation_due_at: string | null;
  expires_at: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  account_health_label: string;
  can_use_for_live_fetch: boolean;
  warning_summary_json: Record<string, unknown> | null;
  browser_context_available: boolean;
  browser_context_status: string | null;
  browser_context_id: string | null;
  browser_context_last_used_at: string | null;
  manual_import_preflight: DouyinManualImportPreflight | null;
  browser_health_alignment: DouyinBrowserHealthAlignment;
  metadata_json: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type DouyinAccountListResponse = {
  accounts: DouyinAccount[];
};

export type DouyinAccountCreateRequest = {
  display_name: string;
  session_cookie: string;
  user_agent?: string | null;
  proxy_url?: string | null;
  is_default?: boolean;
  metadata_json?: Record<string, unknown> | null;
  notes?: string | null;
};

export type DouyinAccountUpdateRequest = Partial<{
  display_name: string;
  session_cookie: string;
  user_agent: string | null;
  proxy_url: string | null;
  status: DouyinAccountStatus;
  is_default: boolean;
  metadata_json: Record<string, unknown> | null;
  notes: string | null;
}>;

export type DouyinAccountValidationResponse = {
  account: DouyinAccount;
  valid: boolean;
  status: DouyinAccountStatus;
  reason: string;
  douyin_user_id: string | null;
};

export type DouyinAccountChallengeActionResponse = {
  account: DouyinAccount;
  action: string;
  challenge_state: string | null;
  challenge_category: string | null;
  recommended_next_action: string | null;
  valid: boolean | null;
  reason: string | null;
  post_challenge_recheck_result: string | null;
  same_profile_reused: boolean | null;
  same_runtime_reused: boolean | null;
  runtime_reopened_for_recheck: boolean | null;
  intake_ready_after_recheck: boolean | null;
};

export type DouyinCurrentPageType =
  | "login_page"
  | "challenge_page"
  | "home_feed_page"
  | "profile_page"
  | "profile_feed_page"
  | "video_detail_page"
  | "unsupported_page"
  | "unknown_page";

export type DouyinCurrentPageDetectionResponse = {
  diagnostics_id: string;
  account_connection_id: string;
  detected_page_type: DouyinCurrentPageType;
  supported_capture: boolean;
  recommended_action: string;
  recommended_action_label: string;
  operator_message: string;
  page_url: string | null;
  normalized_profile_url: string | null;
  title: string | null;
  video_link_count: number;
  runtime_context_id: string | null;
  runtime_attach_status: string | null;
  page_recovery_status: string | null;
  managed_runtime_status: string | null;
  detected_at: string;
  reason: string | null;
};

export type DouyinCurrentPageCaptureRequest = {
  workspace_id?: string | null;
  preset_name?: string | null;
  filter_config?: Record<string, unknown> | null;
  persist?: boolean;
  max_videos?: number;
};

export type DouyinCurrentPageCaptureResponse = {
  success: boolean;
  diagnostics_id: string;
  account_connection_id: string;
  detected_page_type: DouyinCurrentPageType;
  source_profile_id: string;
  crawl_session_id: string | null;
  submitted_profile_url: string;
  normalized_profile_identifier: string | null;
  videos_discovered_count: number;
  videos_created_count: number;
  videos_updated_count: number;
  candidates_total_count: number;
  candidates_matched_count: number;
  candidates_rejected_count: number;
  candidate_results_count: number;
  filters_applied_summary: Record<string, unknown>;
  unsupported_filters_ignored: string[];
  fetch_mode: string;
  used_existing_profile: boolean;
  douyin_account_connection_id: string;
  selected_douyin_account_connection_id: string;
  resolved_douyin_account_connection_id: string;
  fetch_stage: string | null;
  fetch_stage_code: string | null;
  fetch_stage_message: string | null;
  parser_strategy: string | null;
  fetch_execution_path: string | null;
  fallback_from_execution_path: string | null;
  strategy_policy: string | null;
  primary_execution_path: string | null;
  http_fallback_attempted: boolean | null;
  http_fallback_reason: string | null;
  preflight_ran: boolean;
  videos_normalized_count: number;
  videos_persisted_count: number;
  next_suggested_route: string;
  warning: string | null;
  discovered_at: string;
  current_page_url: string | null;
  current_page_title: string | null;
  current_page_video_link_count: number;
};

export type DouyinAccountRevalidateRequest = {
  workspace_id?: string | null;
  due_only?: boolean;
};

export type DouyinAccountRevalidateResponse = {
  accounts_checked: number;
  accounts_updated: number;
  accounts: DouyinAccount[];
};

export type DouyinAccountRevalidateJobResponse = {
  job_id: string;
  job_type: string;
  queued_accounts_count: number | null;
};

export type DouyinAccountDeleteResponse = {
  deleted_account_id: string;
  delete_mode: "soft_delete" | "hard_delete" | string;
  success: boolean;
  warnings: string[];
  recommended_follow_up: string | null;
};

export type DouyinBrowserConnectSessionStatus =
  | "PENDING"
  | "LAUNCHING_BROWSER"
  | "WAITING_FOR_LOGIN"
  | "CAPTURING_SESSION"
  | "VALIDATING"
  | "COMPLETED"
  | "FAILED"
  | "CANCELLED";

export type DouyinBrowserConnectStartRequest = {
  account_connection_id?: string | null;
  display_name?: string | null;
  user_agent?: string | null;
  proxy_url?: string | null;
  is_default?: boolean;
  timeout_seconds?: number;
};

export type DouyinBrowserConnectOutcome = "running" | "completed" | "failed" | "timed_out" | "cancelled";

export type DouyinBrowserConnectPhase =
  | "starting_browser"
  | "waiting_for_login"
  | "login_detected"
  | "stabilizing_auth"
  | "capturing_session"
  | "validating_session"
  | "validation_retry_ready"
  | "completed"
  | "failed"
  | "cancelled";

export type DouyinBrowserConnectSession = {
  id: string;
  workspace_id: string;
  status: DouyinBrowserConnectSessionStatus;
  mode: string;
  display_name: string | null;
  started_at: string | null;
  finished_at: string | null;
  last_error: string | null;
  error_code: string | null;
  error_message: string | null;
  outcome: DouyinBrowserConnectOutcome;
  phase: DouyinBrowserConnectPhase;
  phase_deadline_at: string | null;
  remaining_seconds: number | null;
  timed_out_at: string | null;
  age_seconds: number | null;
  is_stale: boolean;
  stale_reason: string | null;
  can_retry: boolean;
  can_cancel: boolean;
  can_resume: boolean;
  can_force_restart: boolean;
  can_resume_browser_session: boolean;
  can_retry_validation: boolean;
  should_keep_browser_open: boolean;
  validation_attempt_count: number;
  next_action: string | null;
  runtime_available: boolean | null;
  manual_fallback_available: boolean;
  derived_account_id: string | null;
  account: DouyinAccount | null;
  instructions: string;
  login_url: string;
};

export type DouyinBrowserConnectActiveSessionResponse = {
  session: DouyinBrowserConnectSession | null;
};

export type DouyinBrowserConnectResetResponse = {
  reset_count: number;
  affected_session_ids: string[];
  resulting_state: DouyinBrowserConnectSessionStatus;
  can_start_new: boolean;
  warning: string | null;
};
