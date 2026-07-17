export type IntakeFilterConfig = {
  date_mode?: "absolute_range";
  start_date?: string;
  end_date?: string;
  min_views?: number;
  max_views?: number;
  min_likes?: number;
  max_likes?: number;
  min_comments?: number;
  max_comments?: number;
  min_shares?: number;
  max_shares?: number;
  min_duration_seconds?: number;
  max_duration_seconds?: number;
  min_engagement_rate?: number;
  max_engagement_rate?: number;
  has_speech?: boolean;
  max_text_density?: "low" | "medium" | "high";
  exclude_heavy_watermark?: boolean;
  exclude_high_processing_complexity?: boolean;
  exclude_high_copyright_risk?: boolean;
  sort: "score_desc";
  limit: number;
  offset: number;
};

export type IntakeDiscoverRequest = {
  profile_url: string;
  preset_name: string | null;
  filter_config: IntakeFilterConfig;
  persist: boolean;
  force_live_refresh: boolean;
  douyin_account_connection_id: string | null;
};

export type IntakeReadyCheckRequest = {
  workspace_id?: string | null;
  profile_url?: string | null;
  douyin_account_connection_id?: string | null;
};

export type IntakeReadyCheckResponse = {
  diagnostics_id: string;
  readiness_status: "READY" | "READY_AFTER_REOPEN" | "FALLBACK_READY" | "CHALLENGE_BLOCKED" | "PROFILE_QUARANTINED" | "NOT_READY" | string;
  safe_to_run_intake_now: boolean;
  selected_account_id: string | null;
  selected_account_label: string | null;
  resolved_account_id: string | null;
  resolved_account_label: string | null;
  account_selection_mode: string | null;
  account_selection_reason: string | null;
  account_fallback_notice: string | null;
  account_health: string | null;
  browser_profile_status: string | null;
  browser_profile_available: boolean;
  browser_reopen_needed: boolean;
  browser_reopen_attempted: boolean;
  browser_reopen_result: string | null;
  intended_fetch_path: string | null;
  fallback_allowed: boolean;
  recommended_action: string;
  recommended_action_label: string;
  summary_message: string;
  preflight_cached: boolean;
  watchdog_result: string | null;
  watchdog_status: string | null;
  watchdog_reason: string | null;
  preflight_result: string | null;
  fetch_readiness_category: string | null;
  preflight_failure_code: string | null;
  preflight_failure_message: string | null;
  challenge_state: string | null;
  challenge_category: string | null;
  challenge_count: number | null;
  challenge_cooldown_until: string | null;
  challenge_recommended_next_action: string | null;
  profile_quarantine_state: string;
  profile_quarantine_reason: string | null;
  profile_quarantine_detected: boolean;
  profile_quarantine_recommended_next_action: string | null;
  profile_quarantine_blocks_primary_flow: boolean;
  profile_quarantine_replaced_by_account_id: string | null;
  profile_quarantine_clean_profile_recommendation: string | null;
  profile_url: string | null;
};

export type IntakeDiscoverResponse = {
  success: boolean;
  diagnostics_id: string;
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
  douyin_account_connection_id: string | null;
  selected_douyin_account_connection_id: string | null;
  resolved_douyin_account_connection_id: string | null;
  douyin_account_selection_mode: string | null;
  douyin_account_selection_reason: string | null;
  douyin_account_fallback_notice: string | null;
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
  preflight_result: string | null;
  fetch_readiness_category: string | null;
  selected_fetch_path: string | null;
  browser_reopen_attempted: boolean | null;
  browser_reopen_result: string | null;
  preflight_failure_code: string | null;
  preflight_cached: boolean | null;
  watchdog_result: string | null;
  watchdog_status: string | null;
  watchdog_reason: string | null;
  runtime_reconciled: boolean | null;
  videos_normalized_count: number;
  videos_persisted_count: number;
  next_suggested_route: string;
  warning: string | null;
  discovered_at: string;
};

export type IntakeSavedPresetPayload = {
  profile_url: string;
  preset_name: string | null;
  filter_config: IntakeFilterConfig;
  force_live_refresh: boolean;
  douyin_account_connection_id: string | null;
};

export type IntakeSavedPresetCreateRequest = IntakeSavedPresetPayload & {
  workspace_id?: string | null;
  name: string;
  notes?: string | null;
};

export type IntakeSavedPresetUpdateRequest = {
  name?: string;
  profile_url?: string;
  preset_name?: string | null;
  filter_config?: IntakeFilterConfig;
  force_live_refresh?: boolean;
  douyin_account_connection_id?: string | null;
  notes?: string | null;
};

export type IntakeSavedPresetResponse = {
  id: string;
  workspace_id: string;
  name: string;
  profile_url: string;
  preset_name: string | null;
  filter_config: Record<string, unknown>;
  force_live_refresh: boolean;
  douyin_account_connection_id: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type IntakeSavedPresetListResponse = {
  presets: IntakeSavedPresetResponse[];
};

export type IntakeRecentProfileResponse = {
  source_profile_id: string;
  profile_url: string;
  normalized_profile_identifier: string | null;
  display_name: string | null;
  last_crawled_at: string | null;
};

export type IntakeLatestSuccessShortcutResponse = {
  crawl_session_id: string;
  source_profile_id: string | null;
  submitted_profile_url: string | null;
  normalized_profile_identifier: string | null;
  finished_at: string | null;
  videos_discovered_count: number;
};

export type IntakeBootstrapResponse = {
  workspace_id: string;
  saved_presets: IntakeSavedPresetResponse[];
  recent_profiles: IntakeRecentProfileResponse[];
  latest_success_shortcuts: IntakeLatestSuccessShortcutResponse[];
};

export type IntakeRunSummaryResponse = {
  crawl_session_id: string;
  source_profile_id: string | null;
  submitted_profile_url: string | null;
  normalized_profile_identifier: string | null;
  source_profile_display_name: string | null;
  status: string;
  fetch_mode: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_seconds: number | null;
  videos_discovered_count: number;
  videos_created_count: number;
  videos_updated_count: number;
  candidates_total_count: number;
  candidates_matched_count: number;
  error_code: string | null;
  error_message: string | null;
};

export type IntakeRunListResponse = {
  runs: IntakeRunSummaryResponse[];
};

export type IntakeTroubleshootingSummaryResponse = {
  category: string;
  severity: string;
  why: string;
  recommended_actions: string[];
};

export type IntakeRunDetailResponse = IntakeRunSummaryResponse & {
  troubleshooting: IntakeTroubleshootingSummaryResponse;
};

export type IntakeRunCompareResponse = {
  left: IntakeRunSummaryResponse;
  right: IntakeRunSummaryResponse;
  status_changed: boolean;
  duration_seconds_delta: number | null;
  videos_discovered_delta: number;
  videos_created_delta: number;
  videos_updated_delta: number;
  error_code_changed: boolean;
  left_error_code: string | null;
  right_error_code: string | null;
  left_candidates_total: number;
  right_candidates_total: number;
  candidates_total_delta: number;
  left_candidates_matched: number;
  right_candidates_matched: number;
  candidates_matched_delta: number;
};

export type IntakeFormValues = {
  profileUrl: string;
  dateFrom: string;
  dateTo: string;
  minViews: string;
  maxViews: string;
  minLikes: string;
  maxLikes: string;
  minComments: string;
  maxComments: string;
  minShares: string;
  maxShares: string;
  minDurationSeconds: string;
  maxDurationSeconds: string;
  minEngagementRate: string;
  maxEngagementRate: string;
  hasSpeech: "any" | "yes" | "no";
  maxTextDensity: "" | "low" | "medium" | "high";
  excludeHeavyWatermark: boolean;
  excludeHighProcessingComplexity: boolean;
  excludeHighCopyrightRisk: boolean;
  forceLiveRefresh: boolean;
  douyinAccountConnectionId: string;
  presetName: string;
};

export type IntakeValidationErrors = Partial<Record<keyof IntakeFormValues | "form", string>>;

export type RecentIntakeSetup = {
  profileUrl: string;
  presetName: string;
  discoveredAt: string;
};
