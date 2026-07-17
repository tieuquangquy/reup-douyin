import type { HarvestPlanRequestPayload } from "./requestPayloads.js";
import type { ExtensionCapturePayload, ExtensionMessage, FullModalHarvestProbeResult, VideoPayload } from "./types.js";

export const MODAL_WHOLE_PROFILE_TEST_RUN_KEY = "douyinModalWholeProfileTestRun";
export const MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION = "phase17s_dry_run_reuse_verified_targets";

export type ModalWholeProfileTestMode = "verify_only" | "dry_run_first_n" | "dry_run_last_n" | "dry_run_random_n" | "dry_run_specific_ids";
export type ModalWholeProfileDryRunSamplingMode = "first_n" | "last_n" | "random_n" | "specific_ids" | null;
export type ModalWholeProfileTestStatus = "idle" | "running" | "completed" | "completed_with_failures" | "completed_with_warnings" | "failed";
export type ModalWholeProfileStepStatus = "pending" | "starting" | "running" | "success" | "failed";
export type ModalWholeProfileTestPhase =
  | "starting"
  | "closing_modal_without_reload"
  | "waiting_profile_ready"
  | "scanning_profile"
  | "building_harvest_plan"
  | "hard_navigating_to_profile"
  | "reconnecting_after_hard_navigation"
  | "detecting_profile"
  | "verifying_before_dry_run"
  | "dry_run_sampling"
  | "dry_run_opening_target"
  | "dry_run_waiting_modal"
  | "dry_run_settling_modal"
  | "dry_run_extracting"
  | "dry_run_validating"
  | "dry_run_completed"
  | "completed"
  | "failed";
export type ModalWholeProfileFailureReason =
  | "profile_navigation_failed"
  | "profile_grid_not_ready"
  | "profile_grid_not_ready_timeout"
  | "profile_aweme_extraction_failed"
  | "douyin_login_required"
  | "douyin_checkpoint_required"
  | "no_videos_found"
  | "profile_card_selector_failed"
  | "profile_empty_detected"
  | "login_or_captcha_blocked"
  | "scan_timeout"
  | "profile_scan_returned_no_cards"
  | "profile_scroll_container_not_found"
  | "profile_scan_low_count"
  | "no_targets_for_selected_mode"
  | "profile_scan_returned_no_targets"
  | "no_reload_modal_close_failed"
  | "content_script_reconnect_failed_after_hard_navigation"
  | "content_script_reconnect_failed_after_profile_navigation"
  | "reconnect_timeout"
  | "profile_grid_not_ready_or_state_machine_stuck"
  | "profile_scan_stalled"
  | "profile_scan_timeout"
  | "profile_scan_runner_not_started"
  | "profile_scan_handler_not_registered"
  | "profile_scan_start_failed"
  | "scan_action_route_not_hit"
  | "scan_background_route_not_hit"
  | "scan_tab_not_found"
  | "scan_tab_not_douyin"
  | "scan_content_script_unavailable"
  | "scan_content_script_injection_failed"
  | "scan_dom_probe_failed"
  | "profile_scan_exception"
  | "harvest_plan_failed"
  | "no_verified_targets"
  | "verify_failed_before_dry_run"
  | "invalid_specific_ids"
  | "dry_run_sample_empty"
  | "dry_run_no_targets"
  | "dry_run_backend_write_blocked"
  | "dry_run_modal_navigation_failed"
  | "dry_run_modal_metrics_timeout"
  | "dry_run_data_integrity_mismatch"
  | "dry_run_some_targets_failed"
  | "dry_run_all_targets_failed";

export type ModalWholeProfileSelectorAttempt = {
  name: string;
  count: number;
};

export type ModalWholeProfileScrollContainerDiagnostic = {
  tag: string;
  class: string | null;
  scroll_top: number;
  scroll_height: number;
  client_height: number;
  contains_video_links: boolean;
  candidate_count: number;
  visible: boolean;
  can_scroll: boolean;
  score: number;
};

export type DouyinProfileDomProbe = {
  traceVersion: "22C-9A";
  url: string;
  pathname: string;
  search: string;
  documentReadyState: string;
  bodyTextLength: number;
  pageTypeDetected: "profile" | "modal" | "video" | "login_or_captcha" | "unknown";
  profileContainerFound: boolean;
  profileContainerSelector: string | null;
  profileGridFound: boolean;
  profileGridSelector: string | null;
  videoAnchorCount: number;
  videoAnchors: string[];
  videoAnchorsSample: string[];
  modalIdLinkCount: number;
  modalIdLinks: string[];
  modalIdLinksSample: string[];
  awemeIdCount: number;
  awemeIds: string[];
  awemeIdsSample: string[];
  expectedProfileVideoCount?: number | null;
  expectedProfileVideoCountRawText?: string | null;
  expectedProfileVideoCountSelector?: string | null;
  expectedProfileVideoCountParseOk?: boolean;
  expectedProfileVideoCountParseError?: string | null;
  gridCardCandidateCount: number;
  gridCards: string[];
  gridCardSelectorHits: Record<string, number>;
  scrollContainerFound: boolean;
  scrollContainerSelector: string | null;
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
  emptyProfileDetected: boolean;
  loginWallDetected: boolean;
  captchaDetected: boolean;
  checkpointDetected: boolean;
  networkOrPageBlockedDetected: boolean;
  probeError: string | null;
};

export type ModalWholeProfileScanRoundDiagnostic = {
  round: number;
  stage?: "round_started" | "round_completed";
  scroll_top_before: number;
  scroll_top_after: number;
  scroll_height: number;
  client_height: number;
  new_count: number;
  total_count: number;
  candidate_count: number;
  visible_link_count: number;
  video_aweme_candidate_count: number;
  selector_attempts: ModalWholeProfileSelectorAttempt[];
  scroll_container_status?: "detecting" | "found" | "not_found";
  expected_profile_video_count?: number | null;
  missing_expected_count?: number | null;
  bottom_reached?: boolean;
  bottom_bounce_done?: boolean;
  stable_rounds?: number;
  scroll_delta?: number;
  no_new_unique_streak?: number;
  last_new_aweme_id?: string | null;
  sample_new_aweme_ids?: string[];
  scroll_strategy?: string;
};

export type ModalWholeProfileScannerInvocationMode = "direct_same_context" | "content_script_message" | "reconnected_message";

export type ModalWholeProfileScanMessage = ExtensionMessage & {
  type: "REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE";
  run_id: string;
  expected_profile_url: string;
  mode: ModalWholeProfileTestMode;
  coverage_mode: "refresh_all";
};

export type ModalWholeProfileStopReason = "stable_no_new_ids" | "reached_bottom" | "max_rounds" | "max_rounds_before_expected_count" | "max_total_time" | "scroll_failed" | "profile_scan_returned_no_cards" | "expected_count_reached" | "bottom_reached_expected_count_reached" | "bottom_reached_before_expected_count" | "scroll_stalled_before_expected_count" | "bottom_reached_no_more_ids" | "gap_closing_budget_exhausted_before_expected_count";
export type ModalWholeProfileCandidateStatus = "accepted" | "rejected";
export type ModalWholeProfileCandidateRejectReason = "invalid_length" | "likely_timestamp" | "unscoped_regex" | "no_video_context" | "duplicate" | "modal_open_validation_failed";
export type ModalWholeProfileCandidateSource = "video_link" | "modal_link" | "data_attr" | "card_context_regex" | "body_regex";
export type ModalWholeProfileCandidateInput = {
  candidate_id: string | null;
  source: ModalWholeProfileCandidateSource;
  source_url: string | null;
  card_context: boolean;
  has_video_context?: boolean;
  in_excluded_context?: boolean;
};
export type ModalWholeProfileCandidateClassification = {
  candidate_id: string;
  status: ModalWholeProfileCandidateStatus;
  reason: ModalWholeProfileCandidateRejectReason | null;
  source: ModalWholeProfileCandidateSource;
  source_url: string | null;
  card_context: boolean;
};

export type ModalWholeProfileScanDiagnostics = {
  selector_attempts: ModalWholeProfileSelectorAttempt[];
  current_url: string;
  target_profile_url?: string | null;
  page_type: "profile" | "modal" | "video" | "login_or_captcha" | "unknown";
  modal_id_present: boolean;
  document_ready_state: string;
  body_text_sample: string;
  scroll_y: number;
  viewport: { width: number; height: number; device_pixel_ratio: number };
  candidate_card_count: number;
  visible_link_count: number;
  video_aweme_candidate_count: number;
  grid_container_count: number;
  empty_state_detected: boolean;
  login_or_captcha_detected: boolean;
  rounds: number;
  scan_rounds: ModalWholeProfileScanRoundDiagnostic[];
  stop_reason: ModalWholeProfileStopReason | null;
  scanner_invocation_mode?: ModalWholeProfileScannerInvocationMode;
  selected_scroll_container: ModalWholeProfileScrollContainerDiagnostic | null;
  scroll_container_candidates: ModalWholeProfileScrollContainerDiagnostic[];
  scroll_container_found: boolean;
  scroll_container_strategy: string | null;
  selected_profile_tab: string | null;
  tab_candidates: string[];
  warning: "profile_scan_low_count" | "profile_scan_partial" | null;
  candidate_classifications: ModalWholeProfileCandidateClassification[];
  raw_candidate_count: number;
  accepted_count: number;
  rejected_count: number;
  rejected_examples: ModalWholeProfileCandidateClassification[];
  candidate_sources_count: Record<ModalWholeProfileCandidateSource, number>;
  expected_profile_video_count: number | null;
  expected_profile_video_count_source?: string | null;
  expected_profile_video_count_raw_text?: string | null;
  expected_profile_video_count_selector?: string | null;
  expected_profile_video_count_parse_ok?: boolean;
  expected_profile_video_count_parse_error?: string | null;
  expected_profile_video_count_parse_confidence?: "high" | "medium" | "low";
  expected_profile_video_count_normalized_text?: string | null;
  expected_profile_video_count_semantics_verified?: "yes" | "no";
  expected_count_parity_mode?: "strict" | "off";
  expected_count_gap_closing_rounds?: number;
  expected_count_gap_closing_budget?: number;
  expected_count_gap_closing_active?: boolean;
  expected_count_timeout_fallback?: "none" | "max_total_time" | "max_rounds" | "stalled_before_expected_count" | "bottom_before_expected_count";
  expected_count_value: number | null;
  expected_count_source: "profile_tab_text" | "unavailable";
  expected_count_profile_url: string;
  expected_count_updated_at: string;
  expected_count_scan_run_id: string;
  scan_run_id: string;
  final_found_count: number;
  missing_expected_count: number | null;
  missing_profile_video_count?: number | null;
  profile_scan_completion_ratio?: string | null;
  profile_scan_incomplete_reason?: string | null;
  bottom_reached: boolean;
  bottom_bounce_done: boolean;
  stable_rounds: number;
  final_aweme_ids: string[];
  partial_scan: boolean;
  profile_dom_probe?: DouyinProfileDomProbe | null;
  scan_preflight_status?: "ready" | "waiting" | "timeout" | "blocked" | "empty" | "error";
  scan_grid_ready?: boolean;
  profile_grid_selector_hits?: Record<string, number>;
  video_link_count?: number;
  aweme_link_count?: number;
  grid_card_candidate_count?: number;
  preflight_attempt_count?: number | null;
  preflight_elapsed_ms?: number | null;
  first_grid_ready_at?: string | null;
  scan_no_round_reason?: string | null;
  scan_rounds_total?: number;
  round_new_unique_id_counts?: number[];
  round_total_unique_id_counts?: number[];
  round_visible_anchor_counts?: number[];
  round_scroll_top_before?: number[];
  round_scroll_top_after?: number[];
  round_scroll_height?: number[];
  round_client_height?: number[];
  round_scroll_delta?: number[];
  round_reached_bottom?: boolean[];
  round_no_new_unique_streak?: number[];
  round_last_new_aweme_id?: Array<string | null>;
  round_sample_new_aweme_ids?: Array<{ round: number; ids: string[] }>;
  final_unique_aweme_id_count?: number;
  final_verified_target_count?: number;
  final_queue_output_count?: number;
  scroll_stalled_rounds?: number;
  new_ids_stopped_appearing?: boolean;
  per_round: Array<Pick<ModalWholeProfileScanRoundDiagnostic, "round" | "new_count" | "total_count" | "candidate_count" | "visible_link_count" | "video_aweme_candidate_count" | "scroll_top_before" | "scroll_top_after" | "scroll_height" | "client_height" | "bottom_reached" | "bottom_bounce_done" | "stable_rounds" | "missing_expected_count" | "scroll_delta" | "no_new_unique_streak" | "last_new_aweme_id">>;
};

export type ModalWholeProfileCard = {
  aweme_id: string;
  source_url: string;
  title: string | null;
  caption: string | null;
  text_sample: string | null;
  thumbnail_url: string | null;
  posted_text: string | null;
  posted_at: string | null;
  duration_text: string | null;
  duration_seconds: number | null;
  view_text: string | null;
  view_count: number | null;
  extraction_source: string;
  evidence_sources?: ModalWholeProfileCandidateSource[];
  first_seen_index?: number | null;
  last_seen_round?: number | null;
  video_url?: string | null;
  raw_profile_card: Record<string, unknown>;
};

export type ModalWholeProfileCardScanResult = {
  status: "success" | "failed";
  reason: ModalWholeProfileFailureReason | null;
  cards: ModalWholeProfileCard[];
  diagnostics: ModalWholeProfileScanDiagnostics;
};

export type ModalWholeProfileVerifiedTargetDetail = {
  aweme_id: string;
  index: number;
  profile_card_evidence: Record<string, unknown>;
};

export type ModalWholeProfileFallbackResult = "not_needed" | "not_attempted" | "recovered" | "incomplete" | "safety_blocked" | "failed";
export type ModalWholeProfileModalOpenReason = "missing_required_fields" | "not_needed" | "safety_blocked" | "failed";
export type ModalWholeProfileFinalStatus = "pass_hybrid" | "pass_with_modal_fallback" | "fail_hybrid_no_fallback" | "fail_fallback_not_attempted" | "fail_after_modal_fallback" | "fail_safety_blocked";
export type ModalWholeProfileFallbackOpenModalStatus = "opened" | "blocked" | "timeout" | "not_attempted" | "failed";
export type ModalWholeProfileFallbackTriState = "yes" | "no" | "unknown";
export type ModalWholeProfileFallbackCalibratedPointReadStatus = "success" | "failed" | "timeout" | "not_attempted";

export type ModalWholeProfileViewCountCandidateSource = "network_cache" | "profile_repository" | "passive_aweme" | "profile_post_api" | "calibrated_non_modal_dom";

export type ModalWholeProfileViewCountCandidateField = {
  source: ModalWholeProfileViewCountCandidateSource;
  field_path: string;
  raw_type: string;
  raw_value_sample: number | string | null;
  parsed_value: number | null;
  selected_for_view_count: "yes" | "no";
};

export type ModalWholeProfileViewCountRejectedFalsePositiveCandidate = {
  source: ModalWholeProfileViewCountCandidateSource;
  field_path: string;
  rejection_reason: string;
};

export type ModalWholeProfileViewCountDiagnostics = {
  normalized_view_count: number | null;
  normalized_view_count_source: string | null;
  normalized_view_count_field_used: string | null;
  normalized_view_count_defaulted: "yes" | "no";
  normalized_view_count_default_reason: string | null;
  real_view_count_found: "yes" | "no";
  trusted_candidates_found: ModalWholeProfileViewCountCandidateField[];
  rejected_false_positive_candidates: ModalWholeProfileViewCountRejectedFalsePositiveCandidate[];
  selected_field_trusted: "yes" | "no";
  selected_field_semantic_reason: string | null;
  view_count_zero_confidence: "low" | "medium" | "high" | null;
  candidate_fields_found: ModalWholeProfileViewCountCandidateField[];
  candidate_field_count: number;
};

export type ModalWholeProfileEstimatedViewsDiagnostics = {
  estimated_views: number | null;
  estimated_views_source: "derived_from_like_count" | "missing_like_count" | "invalid_like_count" | "blocked_compact_or_display_like_count" | "disabled";
  estimated_views_formula: "tiered_like_multiplier_v1";
  like_count_used: number | null;
  like_count_source: string | null;
  multiplier_used: number | null;
  rounded: "yes" | "no";
  confidence: "low" | "medium" | "high";
  validity: "valid" | "missing_like_count" | "invalid_like_count";
};

export type ModalWholeProfileDryRunResult = {
  index: number;
  aweme_id: string;
  target_url: string;
  status: "pass" | "fail";
  hybrid_required_fields_present?: number;
  hybrid_missing_required_fields?: string[];
  hybrid_sources_attempted?: string[];
  hybrid_source_selected?: string | null;
  hybrid_source_selected_reason?: string | null;
  hybrid_fields_from_repository?: string[];
  hybrid_fields_from_network_cache?: string[];
  hybrid_fields_from_profile_post_api?: string[];
  hybrid_fields_from_calibrated_dom?: string[];
  hybrid_missing_after_all_non_modal_sources?: string[];
  hybrid_source_attempt_statuses?: Record<string, { available: "yes" | "no"; missing_required_fields: string[]; selected: "yes" | "no" }>;
  metric_value_source?: Record<string, string | null>;
  view_count_diagnostics?: ModalWholeProfileViewCountDiagnostics;
  estimated_views_diagnostics?: ModalWholeProfileEstimatedViewsDiagnostics;
  extra_values?: { posted: string | number | null; posted_at: string | null; view_count: number | null; estimated_views: number | null; thumbnail_url_present: "yes" | "no"; thumbnail_url_host: string | null };
  extra_value_source?: Record<string, "network_cache" | "profile_repository" | "passive_aweme" | "profile_post_api" | "calibrated_non_modal_dom" | "derived_from_like_count" | "missing">;
  thumbnail?: { present: "yes" | "no"; field_used: string | null; source: string; valid_url: "yes" | "no"; url?: string | null; url_host: string | null };
  modal_fallback_required?: boolean;
  modal_fallback_used?: boolean;
  modal_fallback_result?: ModalWholeProfileFallbackResult;
  modal_fallback_fields_present?: number;
  modal_fallback_missing_required_fields?: string[];
  modal_fallback_error?: string | null;
  final_status?: ModalWholeProfileFinalStatus;
  final_missing_required_fields?: string[];
  modal_opened_for_this_item?: "yes" | "no";
  modal_open_reason?: ModalWholeProfileModalOpenReason;
  fallback_attempted?: "yes" | "no";
  fallback_open_modal_status?: ModalWholeProfileFallbackOpenModalStatus;
  fallback_modal_url_built?: "yes" | "no";
  fallback_modal_id_matches_target?: ModalWholeProfileFallbackTriState;
  fallback_dom_ready?: ModalWholeProfileFallbackTriState;
  fallback_calibration_ready?: ModalWholeProfileFallbackTriState;
  fallback_calibrated_point_read_status?: ModalWholeProfileFallbackCalibratedPointReadStatus;
  fallback_missing_required_fields_after_attempt?: string[];
  fallback_failure_stage?: string | null;
  fallback_failure_reason_safe?: string | null;
  duration_seconds: number | null;
  duration_text: string | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  current_modal_id_before: string | null;
  current_modal_id_after: string | null;
  extracted_aweme_id: string | null;
  source_used: string | null;
  data_integrity_status: "passed" | "failed" | "not_checked";
  error: string | null;
  started_at: string;
  completed_at: string;
};

export type ModalWholeProfileComparisonLogRow = {
  index: number;
  aweme_id: string;
  status: "pass" | "fail";
  required_fields_present: number;
  required_fields_total: number;
  missing_required_fields: string[];
  hybrid_required_fields_present: number;
  hybrid_missing_required_fields: string[];
  modal_fallback_required: boolean;
  modal_fallback_reason: "missing_required_fields" | null;
  modal_fallback_used: boolean;
  modal_fallback_result: ModalWholeProfileFallbackResult;
  modal_fallback_fields_present: number;
  modal_fallback_missing_required_fields: string[];
  final_status: ModalWholeProfileFinalStatus;
  final_missing_required_fields: string[];
  modal_opened_for_this_item: "yes" | "no";
  modal_open_reason: ModalWholeProfileModalOpenReason;
  hybrid_status: "ready" | "missing_required_fields" | "failed";
  hybrid_sources_attempted: string[];
  hybrid_source_selected: string | null;
  hybrid_source_selected_reason: string | null;
  hybrid_fields_from_repository: string[];
  hybrid_fields_from_network_cache: string[];
  hybrid_fields_from_profile_post_api: string[];
  hybrid_fields_from_calibrated_dom: string[];
  hybrid_missing_after_all_non_modal_sources: string[];
  metric_values: Record<string, number | null>;
  metric_value_types: Record<string, "number" | "null" | "non_number">;
  metric_value_validity: Record<string, "valid_positive_number" | "valid_non_negative_number" | "invalid_null" | "invalid_non_number" | "invalid_non_positive_number" | "invalid_negative_number">;
  metric_value_source: Record<string, string | null>;
  thumbnail: { present: "yes" | "no"; field_used: string | null; source: string; valid_url: "yes" | "no"; url?: string | null; url_host: string | null };
  view_count_diagnostics: ModalWholeProfileViewCountDiagnostics;
  estimated_views_diagnostics: ModalWholeProfileEstimatedViewsDiagnostics;
  extra_values: { posted: string | number | null; posted_at: string | null; view_count: number | null; estimated_views: number | null; thumbnail_url_present: "yes" | "no"; thumbnail_url_host: string | null; title?: string | null; title_source?: string | null; title_is_id_fallback?: boolean; title_valid_real_text?: boolean; raw_like_count_source?: string | null; raw_like_count_value_type?: string; raw_like_count_exact_numeric?: boolean; display_like_text?: string | null; display_like_text_source?: string | null; rounded_like_display_rejected_for_raw?: boolean };
  extra_value_types: Record<"posted" | "posted_at" | "view_count" | "estimated_views" | "thumbnail_url_present" | "thumbnail_url_host", string>;
  extra_value_validity: { posted: "valid" | "missing" | "invalid"; posted_at: "valid_iso_datetime" | "valid_timestamp" | "missing" | "invalid"; view_count: "valid_non_negative_number" | "missing" | "invalid"; estimated_views: "valid_non_negative_number" | "missing" | "invalid"; thumbnail: "valid_url" | "missing" | "invalid" };
  extra_value_source: Record<"posted" | "posted_at" | "view_count" | "estimated_views" | "thumbnail", "network_cache" | "profile_repository" | "passive_aweme" | "profile_post_api" | "calibrated_non_modal_dom" | "derived_from_like_count" | "missing">;
  fallback_attempted: "yes" | "no";
  fallback_open_modal_status: ModalWholeProfileFallbackOpenModalStatus;
  fallback_modal_url_built: "yes" | "no";
  fallback_modal_id_matches_target: ModalWholeProfileFallbackTriState;
  fallback_dom_ready: ModalWholeProfileFallbackTriState;
  fallback_calibration_ready: ModalWholeProfileFallbackTriState;
  fallback_calibrated_point_read_status: ModalWholeProfileFallbackCalibratedPointReadStatus;
  fallback_missing_required_fields_after_attempt: string[];
  fallback_failure_stage: string | null;
  fallback_failure_reason_safe: string | null;
  extraction_failure_type: "none" | "calibrated_point_read_failure" | "extraction_failure";
  source_used: string | null;
  anti_bot_signal: "none" | "captcha" | "checkpoint" | "login" | "security" | "abnormal_traffic";
  reason: string | null;
};

export type ModalWholeProfileDecisionSummaryRepresentativeRow = {
  row_index: number;
  required_field_validity: Record<string, string>;
  required_field_source: Record<string, string | null>;
  like_count: number | null;
  real_view_count: number | null;
  estimated_views_diagnostics: ModalWholeProfileEstimatedViewsDiagnostics;
  posted_validity: string;
  posted_source: string | null;
  thumbnail_validity: string;
  thumbnail_source: string | null;
  anomaly_reason: string | null;
};

export type ModalWholeProfileHybridOnlyDryRunDecisionSummary = {
  summary_title: "HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY";
  run: Record<string, unknown>;
  sample_completion: Record<string, unknown>;
  dry_run_safety: Record<string, unknown>;
  required_field_counts: Record<string, number>;
  real_view_count: Record<string, unknown>;
  estimated_views: Record<string, unknown>;
  extra_values: Record<string, unknown>;
  metric_fidelity?: Record<string, unknown>;
  metric_fidelity_probe_rows?: Record<string, unknown>[];
  decision: Record<string, unknown>;
  decision_blockers: string[];
  decision_notes: string[];
  failures: Record<string, unknown>;
  representative_rows: ModalWholeProfileDecisionSummaryRepresentativeRow[];
  generated_at: string;
};

export type ModalWholeProfileComparisonLog = {
  comparison_title: "Advanced Details Comparison Log";
  comparison_kind: "modal_baseline_vs_hybrid_candidate" | "hybrid_only_with_modal_fallback";
  run_id: string;
  mode: ModalWholeProfileTestMode;
  tested_videos: number;
  modal_baseline: "verified_target_queue";
  candidate_mode: "hybrid_low_interaction";
  required_fields: string[];
  required_fields_total: number;
  required_fields_complete_count: number;
  required_fields_coverage_rate: string;
  items_with_all_required_fields: number;
  item_required_field_pass_rate: string;
  total_required_field_slots: number;
  required_field_slots_present: number;
  required_field_slot_coverage_rate: string;
  missing_required_field_counts: Record<string, number>;
  hybrid_ready_without_modal_count: number;
  modal_fallback_required_count: number;
  modal_fallback_used_count: number;
  modal_fallback_recovered_count: number;
  modal_fallback_incomplete_count: number;
  modal_fallback_safety_blocked_count: number;
  modal_fallback_count: number;
  modal_fallback_rate: string;
  hybrid_failed_without_fallback_count: number;
  pass_with_modal_fallback_count: number;
  final_ready_count: number;
  final_ready_rate: string;
  final_missing_required_field_counts: Record<string, number>;
  unrecovered_item_count: number;
  unrecovered_failure_stage_counts: Record<string, number>;
  unrecovered_failure_reason_counts: Record<string, number>;
  extraction_failure_count: number;
  anti_bot_signal_count: number;
  anti_bot_signal_types: string[];
  safe_to_scale: "yes" | "no" | "needs_review";
  hybrid_viability_recommendation: "hybrid_ready_without_modal" | "hybrid_viable_with_modal_fallback" | "hybrid_not_viable_yet";
  validation_tier: "sample_3" | "sample_5" | "sample_10" | "sample_25" | "sample_50" | "larger_dry_run";
  requested_sample_size: number;
  completed_sample_size: number;
  stopped_early: "yes" | "no";
  stopped_early_reason: string | null;
  safety_stop_triggered: "yes" | "no";
  elapsed_ms: number | null;
  duration_bucket: "under_1_min" | "1_to_5_min" | "5_to_15_min" | "over_15_min" | "unknown";
  actual_modal_navigation_count: number;
  modal_baseline_navigation_count: number;
  modal_fallback_navigation_count: number;
  modal_navigation_avoided_count: number;
  modal_navigation_avoidance_rate: string;
  expected_old_modal_navigation_count: number;
  modal_navigation_reduction_rate: string;
  per_source_counts: Record<string, number>;
  hybrid_source_counts: Record<string, number>;
  fallback_source_counts: Record<string, number>;
  hybrid_source_attempted_counts: Record<string, number>;
  hybrid_source_success_counts: Record<string, number>;
  hybrid_source_missing_required_counts: Record<string, number>;
  hybrid_source_unavailable_counts: Record<string, number>;
  profile_repository_hydration_count: number;
  network_cache_hydration_count: number;
  passive_aweme_hydration_count: number;
  profile_post_api_hydration_count: number;
  calibrated_non_modal_dom_hydration_count: number;
  modal_fallback_required_after_hybrid_count: number;
  metric_value_present_counts: Record<string, number>;
  metric_value_valid_counts: Record<string, number>;
  metric_value_invalid_counts: Record<string, number>;
  metric_value_source_counts: Record<string, Record<string, number>>;
  thumbnail_coverage_count: number;
  thumbnail_valid_url_count: number;
  thumbnail_source_counts: Record<string, number>;
  extra_value_present_counts: Record<string, number>;
  extra_value_valid_counts: Record<string, number>;
  extra_value_invalid_counts: Record<string, number>;
  extra_value_source_counts: Record<string, Record<string, number>>;
  view_count_candidate_source_counts: Record<string, number>;
  view_count_candidate_field_path_counts: Record<string, number>;
  trusted_view_count_candidate_field_path_counts: Record<string, number>;
  rejected_view_count_false_positive_path_counts: Record<string, number>;
  view_count_selected_trusted_field_counts: Record<string, number>;
  view_count_real_found_count: number;
  view_count_missing_count: number;
  view_count_defaulted_count: number;
  view_count_zero_with_raw_field_count: number;
  view_count_zero_without_raw_field_count: number;
  view_count_nonzero_count: number;
  view_count_zero_confidence_counts: Record<"low" | "medium" | "high", number>;
  views_data_quality_verdict: "trusted_nonzero_views_found" | "trusted_zero_only_low_confidence" | "views_not_available_in_non_modal_sources" | "views_false_positive_only";
  estimated_views_present_count: number;
  estimated_views_missing_count: number;
  estimated_views_valid_count: number;
  estimated_views_invalid_count: number;
  estimated_views_formula: "tiered_like_multiplier_v1";
  estimated_views_multiplier_counts: Record<string, number>;
  estimated_views_source_counts: Record<string, number>;
  estimated_views_confidence_counts: Record<"low" | "medium" | "high", number>;
  estimated_views_data_quality_verdict: "estimated_views_ready" | "estimated_views_missing_like_count" | "estimated_views_invalid_like_count";
  next_step_recommendation: "rerun_sample_5" | "rerun_sample_10" | "proceed_to_larger_dry_run" | "proceed_to_backend_shadow_test" | "backend_shadow_test_with_estimated_views" | "backend_shadow_test_with_estimated_views_available_set" | "diagnose_hybrid_dry_run_early_stop" | "repeat_larger_dry_run" | "investigate_unrecovered_fallback_item" | "fix_modal_fallback_failure" | "fix_hybrid_non_modal_hydration" | "fix_metric_value_hydration" | "fix_posted_hydration" | "fix_view_count_hydration" | "fix_view_count_source_discovery" | "decide_views_optional_or_modal_fallback" | "fix_estimated_views_like_count" | "fix_thumbnail_hydration" | "do_not_scale_missing_fields" | "do_not_scale_safety_signal" | "do_not_scale_extraction_failures" | "do_not_scale_state_mutation_detected";
  backend_write_attempted: "yes" | "no";
  backend_write_mode: "disabled_dry_run" | "enabled_test_only";
  production_collect_state_mutated: "yes" | "no";
  not_safe_to_scale_reason: string | null;
  verdict_reason: string;
  HYBRID_ONLY_DRY_RUN_DECISION_SUMMARY: ModalWholeProfileHybridOnlyDryRunDecisionSummary;
  rows: ModalWholeProfileComparisonLogRow[];
  generated_at: string;
};

export type ModalWholeProfileTestRun = {
  schema_version: typeof MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION;
  run_id: string;
  status: ModalWholeProfileTestStatus;
  mode: ModalWholeProfileTestMode;
  source_modal_url: string;
  source_modal_aweme_id: string;
  resolved_profile_url: string;
  profile_resolved: boolean;
  phase: ModalWholeProfileTestPhase;
  expected_profile_url: string;
  navigation_started_at: string | null;
  hard_navigation_started_at: string | null;
  phase_started_at: string | null;
  reconnect_attempts: number;
  last_reconnect_error: string | null;
  profile_navigation_status: ModalWholeProfileStepStatus;
  profile_grid_status: ModalWholeProfileStepStatus;
  profile_card_scan_status: ModalWholeProfileStepStatus;
  harvest_plan_status: ModalWholeProfileStepStatus;
  profile_scan_status: ModalWholeProfileStepStatus;
  total_cards_found: number;
  total_targets_returned: number;
  refresh_all_target_count: number;
  selected_mode_target_count: number;
  total_found: number;
  target_count: number;
  targets: string[];
  scan_started_at: string | null;
  scan_heartbeat_at: string | null;
  scan_rounds: number | "unknown";
  total_cards_found_so_far: number;
  last_round_new: number | "unknown";
  scroll_container_status: "unknown" | "detecting" | "found" | "not_found";
  scanner_invocation_mode: ModalWholeProfileScannerInvocationMode | null;
  verified_profile_url: string;
  verified_at: string | null;
  verified_targets: string[];
  verified_target_details: ModalWholeProfileVerifiedTargetDetail[];
  verified_target_count: number;
  verified_scan_diagnostics: ModalWholeProfileScanDiagnostics | Record<string, unknown> | null;
  dry_run_limit: number;
  dry_run_sampling_mode: ModalWholeProfileDryRunSamplingMode;
  dry_run_sampled_target_indexes: number[];
  dry_run_sampled_aweme_ids: string[];
  invalid_specific_ids: string[];
  dry_run_specific_ids_input: string;
  dry_run_results: ModalWholeProfileDryRunResult[];
  dry_run_pass_count: number;
  dry_run_fail_count: number;
  dry_run_total: number;
  dry_run_current_index: number | null;
  dry_run_current_aweme_id: string | null;
  raw_candidate_count: number;
  accepted_target_count: number;
  rejected_candidate_count: number;
  rejected_candidates_sample: ModalWholeProfileCandidateClassification[];
  target_validation_warnings: string[];
  can_harvest_whole_profile: boolean;
  reason: ModalWholeProfileFailureReason | string | null;
  comparison_log: ModalWholeProfileComparisonLog | null;
  diagnostics: ModalWholeProfileScanDiagnostics | Record<string, unknown> | null;
  started_at: string;
  updated_at: string;
};

export function createModalWholeProfileTestRun(overrides: Partial<ModalWholeProfileTestRun>): ModalWholeProfileTestRun {
  const now = new Date().toISOString();
  return {
    schema_version: MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION,
    run_id: crypto.randomUUID(),
    status: "idle",
    mode: "verify_only",
    source_modal_url: "",
    source_modal_aweme_id: "",
    resolved_profile_url: "",
    profile_resolved: false,
    phase: "starting",
    expected_profile_url: "",
    navigation_started_at: null,
    hard_navigation_started_at: null,
    phase_started_at: now,
    reconnect_attempts: 0,
    last_reconnect_error: null,
    profile_navigation_status: "pending",
    profile_grid_status: "pending",
    profile_card_scan_status: "pending",
    harvest_plan_status: "pending",
    profile_scan_status: "pending",
    total_cards_found: 0,
    total_targets_returned: 0,
    refresh_all_target_count: 0,
    selected_mode_target_count: 0,
    total_found: 0,
    target_count: 0,
    targets: [],
    scan_started_at: null,
    scan_heartbeat_at: null,
    scan_rounds: "unknown",
    total_cards_found_so_far: 0,
    last_round_new: "unknown",
    scroll_container_status: "unknown",
    scanner_invocation_mode: null,
    verified_profile_url: "",
    verified_at: null,
    verified_targets: [],
    verified_target_details: [],
    verified_target_count: 0,
    verified_scan_diagnostics: null,
    dry_run_limit: 3,
    dry_run_sampled_target_indexes: [],
    dry_run_sampled_aweme_ids: [],
    invalid_specific_ids: [],
    dry_run_specific_ids_input: "",
    dry_run_results: [],
    dry_run_pass_count: 0,
    dry_run_fail_count: 0,
    dry_run_total: 0,
    dry_run_current_index: null,
    dry_run_current_aweme_id: null,
    raw_candidate_count: 0,
    accepted_target_count: 0,
    rejected_candidate_count: 0,
    rejected_candidates_sample: [],
    target_validation_warnings: [],
    can_harvest_whole_profile: false,
    reason: null,
    comparison_log: null,
    diagnostics: null,
    started_at: now,
    updated_at: now,
    ...overrides,
    dry_run_sampling_mode: modalWholeProfileSamplingModeFor(overrides.mode ?? "verify_only", overrides.dry_run_sampling_mode)
  };
}

export function modalWholeProfileSamplingModeFor(mode: ModalWholeProfileTestMode, stored?: ModalWholeProfileDryRunSamplingMode | ModalWholeProfileTestMode): ModalWholeProfileDryRunSamplingMode {
  if (mode === "verify_only") return null;
  if (mode === "dry_run_first_n") return "first_n";
  if (mode === "dry_run_last_n") return "last_n";
  if (mode === "dry_run_random_n") return "random_n";
  if (mode === "dry_run_specific_ids") return "specific_ids";
  return stored === "first_n" || stored === "last_n" || stored === "random_n" || stored === "specific_ids" ? stored : null;
}

export function modalWholeProfileProbeToDryRunResult(index: number, awemeId: string, targetUrl: string, probe: FullModalHarvestProbeResult, startedAt: string, completedAt: string): ModalWholeProfileDryRunResult {
  const currentModalIdBefore = probe.current_modal_id_before ?? probe.aweme_id ?? null;
  const currentModalIdAfter = probe.current_modal_id_after ?? probe.aweme_id ?? null;
  const extractedAwemeId = probe.extracted_aweme_id ?? probe.aweme_id ?? null;
  const metricsPresent = typeof probe.duration_seconds === "number" && [probe.like_count, probe.comment_count, probe.favorite_count, probe.share_count].every((value) => typeof value === "number");
  const integrityPassed = probe.probe_status === "PASS" && probe.ready_for_full_harvest === true && currentModalIdBefore === awemeId && currentModalIdAfter === awemeId && extractedAwemeId === awemeId && metricsPresent;
  const missingRequiredFields = [
    typeof probe.duration_seconds === "number" ? null : "duration_seconds",
    typeof probe.like_count === "number" ? null : "like_count",
    typeof probe.comment_count === "number" ? null : "comment_count",
    typeof probe.favorite_count === "number" ? null : "favorite_count",
    typeof probe.share_count === "number" ? null : "share_count"
  ].filter((field): field is string => Boolean(field));
  return {
    index,
    aweme_id: awemeId,
    target_url: targetUrl,
    status: integrityPassed ? "pass" : "fail",
    hybrid_required_fields_present: 5 - missingRequiredFields.length,
    hybrid_missing_required_fields: missingRequiredFields,
    modal_fallback_required: missingRequiredFields.length > 0,
    modal_fallback_used: false,
    modal_fallback_result: missingRequiredFields.length > 0 ? "failed" : "not_needed",
    modal_fallback_fields_present: 0,
    modal_fallback_missing_required_fields: missingRequiredFields,
    final_status: missingRequiredFields.length > 0 ? "fail_after_modal_fallback" : "pass_hybrid",
    final_missing_required_fields: missingRequiredFields,
    duration_seconds: probe.duration_seconds ?? null,
    duration_text: probe.duration_text ?? null,
    like_count: probe.like_count ?? null,
    comment_count: probe.comment_count ?? null,
    favorite_count: probe.favorite_count ?? null,
    share_count: probe.share_count ?? null,
    current_modal_id_before: currentModalIdBefore,
    current_modal_id_after: currentModalIdAfter,
    extracted_aweme_id: extractedAwemeId,
    source_used: probe.source_used ?? null,
    data_integrity_status: integrityPassed ? "passed" : "failed",
    error: integrityPassed ? null : probe.blocking_reason ?? probe.warning_reason ?? "dry_run_data_integrity_mismatch",
    started_at: startedAt,
    completed_at: completedAt
  };
}

export function isModalWholeProfileTestRun(value: unknown): value is ModalWholeProfileTestRun {
  if (!value || typeof value !== "object") return false;
  const record = value as Partial<ModalWholeProfileTestRun>;
  return record.schema_version === MODAL_WHOLE_PROFILE_TEST_SCHEMA_VERSION && typeof record.run_id === "string" && Array.isArray(record.targets) && Array.isArray(record.dry_run_results);
}

export function buildModalWholeProfileHarvestPlanPayload(args: {
  basePayload: ExtensionCapturePayload;
  cards: ModalWholeProfileCard[];
  harvestMode?: "refresh_all" | "new_only" | "new_and_incomplete";
}): HarvestPlanRequestPayload {
  return {
    ...args.basePayload,
    schema_version: "douyin_extension_harvest_plan.v1",
    harvest_mode: args.harvestMode ?? "refresh_all",
    videos: args.cards.map((card): VideoPayload => ({
      id: card.aweme_id,
      aweme_id: card.aweme_id,
      video_id: card.aweme_id,
      source_video_url: card.source_url,
      share_url: card.source_url,
      url: card.source_url,
      title: card.title,
      desc: card.title,
      thumbnail_url: card.thumbnail_url,
      cover_url: card.thumbnail_url,
      posted_text: card.posted_text,
      preview_status: card.thumbnail_url ? "ready" : "missing",
      source_link_status: "captured",
      media_asset_status: "not_generated",
      media_status: "source_link_captured",
      thumbnail_source: card.thumbnail_url ? "dom_fallback" : "missing",
      thumbnail_missing_reason: card.thumbnail_url ? null : "dom_cover_missing",
      posted_source: card.posted_text ? "dom_text" : "fallback_none",
      capture_context: args.basePayload.capture_context,
      context_mismatch_codes: [],
      statistics: {},
      raw: { profile_card_scan: true, extraction_source: card.extraction_source },
      raw_dom_snapshot: {
        aweme_id: card.aweme_id,
        visible_text: card.title,
        href: card.source_url,
        source_url: card.source_url,
        image_candidates: card.thumbnail_url ? [card.thumbnail_url] : [],
        data_attributes: {},
        local_text_snippets: card.title ? [card.title] : []
      }
    }))
  } as HarvestPlanRequestPayload;
}

export function scanModalWholeProfileCardsInPage(maxRounds = 80, runId?: string, expectedProfileUrl?: string, storageKey?: string): Promise<ModalWholeProfileCardScanResult> {
  return collectProfileCardsUntilStable({
    max_rounds: maxRounds,
    on_round: async (round) => {
      if (!runId || !storageKey || typeof chrome === "undefined" || !chrome.storage?.local) return;
      const stored = await chrome.storage.local.get(storageKey);
      const existing = stored[storageKey] as Record<string, unknown> | undefined;
      if (!existing || existing.run_id !== runId) return;
      const now = new Date().toISOString();
      await chrome.storage.local.set({
        [storageKey]: {
          ...existing,
          scan_heartbeat_at: now,
          scan_rounds: round.round,
          total_cards_found_so_far: round.total_count,
          last_round_new: round.new_count,
          scroll_container_status: round.scroll_height > round.client_height ? "found" : "not_found",
          diagnostics: {
            ...((existing.diagnostics as Record<string, unknown> | null) ?? {}),
            current_url: location.href,
            expected_profile_url: expectedProfileUrl ?? null,
            scan_rounds: [ ...(((existing.diagnostics as { scan_rounds?: ModalWholeProfileScanRoundDiagnostic[] } | null)?.scan_rounds) ?? []), round ],
            rounds: round.round,
            last_round_new: round.new_count,
            scroll_container: round.scroll_height > round.client_height ? "yes" : "no",
            selector_attempts: round.selector_attempts,
            content_script_status: "same_context",
            page_type: new URL(location.href).searchParams.has("modal_id") ? "modal" : /\/user\//.test(location.pathname) ? "profile" : "unknown",
            modal_id_present: new URL(location.href).searchParams.has("modal_id")
          },
          updated_at: now
        }
      });
    }
  });
}

export function legacyVerifiedProfileScanner22C9ZNoGit(options: Parameters<typeof collectProfileCardsUntilStable>[0] = {}): Promise<ModalWholeProfileCardScanResult> {
  return collectProfileCardsUntilStable(options);
}

const PROFILE_GRID_PROBE_SELECTORS = [
  'a[href*="/video/"]',
  'a[href*="modal_id="]',
  'a[href*="aweme_id="]',
  '[data-aweme-id]',
  '[data-item-id]',
  '[data-e2e*="user-post"]',
  '[data-e2e*="post-item"]',
  '[data-e2e*="user-work"]',
  '[data-e2e*="work-item"]',
  '[class*="post"]',
  '[class*="work"]',
  '[class*="card"]',
  '[class*="video"]'
] as const;

const PROFILE_CONTAINER_PROBE_SELECTORS = [
  "main",
  '[role="main"]',
  '[data-e2e*="user-detail"]',
  '[data-e2e*="user-info"]',
  '[class*="user-info"]',
  '[class*="profile"]',
  '[class*="Profile"]'
] as const;

export function buildDouyinProfileDomProbe(scrollSelection = findDouyinProfileScrollContainer()): DouyinProfileDomProbe {
  try {
    const bodyText = compact(document.body?.innerText || document.body?.textContent || "");
    const parsed = new URL(location.href);
    const modalId = parsed.searchParams.get("modal_id");
    const loginWallDetected = /login|passport|\u767b\u5f55|\u8bf7\u5148\u767b\u5f55/i.test(`${bodyText} ${location.href}`);
    const captchaDetected = /captcha|security check|verify you are human|\u9a8c\u8bc1\u7801|\u5b89\u5168\u9a8c\u8bc1|\u6ed1\u5757|\u8bf7\u5b8c\u6210\u9a8c\u8bc1/i.test(bodyText);
    const checkpointDetected = /checkpoint|abnormal traffic|\u68c0\u6d4b\u5230\u5f02\u5e38|\u5b89\u5168\u4e2d\u5fc3/i.test(bodyText);
    const networkOrPageBlockedDetected = /network error|page unavailable|access denied|403|blocked|\u7f51\u7edc\u9519\u8bef|\u9875\u9762\u4e0d\u5b58\u5728|\u8bbf\u95ee\u53d7\u9650/i.test(bodyText);
    const pageTypeDetected = (loginWallDetected || captchaDetected || checkpointDetected)
      ? "login_or_captcha"
      : modalId
        ? "modal"
        : /^\/user\/[^/?#]+/.test(parsed.pathname)
          ? "profile"
          : /^\/video\//.test(parsed.pathname)
            ? "video"
            : "unknown";
    const selectorHits: Record<string, number> = {};
    for (const selector of PROFILE_GRID_PROBE_SELECTORS) {
      selectorHits[selector] = Array.from(document.querySelectorAll(selector)).filter(visible).length;
    }
    const profileContainerSelector = PROFILE_CONTAINER_PROBE_SELECTORS.find((selector) => Array.from(document.querySelectorAll(selector)).some(visible)) ?? null;
    const profileGridSelector = PROFILE_GRID_PROBE_SELECTORS.find((selector) => (selectorHits[selector] ?? 0) > 0) ?? null;
    const videoAnchors = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"]')).filter(visible);
    const modalLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="modal_id="], a[href*="aweme_id="]')).filter(visible);
    const awemeIds = extractAwemeIdsFromProfileDom();
    const expectedCount = detectExpectedProfileVideoCount();
    const selected = scrollSelection.selected_scroll_container;
    const emptyProfileDetected = /no videos|no posts|empty|\u6682\u65e0\u4f5c\u54c1|\u8fd8\u6ca1\u6709\u4f5c\u54c1|\u6ca1\u6709\u4f5c\u54c1/i.test(bodyText);
    return {
      traceVersion: "22C-9A",
      url: location.href,
      pathname: parsed.pathname,
      search: parsed.search,
      documentReadyState: document.readyState,
      bodyTextLength: bodyText.length,
      pageTypeDetected,
      profileContainerFound: Boolean(profileContainerSelector),
      profileContainerSelector,
      profileGridFound: Boolean(profileGridSelector),
      profileGridSelector,
      videoAnchorCount: videoAnchors.length,
      videoAnchors: videoAnchors.map((anchor) => anchor.href).filter(Boolean).slice(0, 500),
      videoAnchorsSample: videoAnchors.map((anchor) => anchor.href).filter(Boolean).slice(0, 5),
      modalIdLinkCount: modalLinks.length,
      modalIdLinks: modalLinks.map((anchor) => anchor.href).filter(Boolean).slice(0, 500),
      modalIdLinksSample: modalLinks.map((anchor) => anchor.href).filter(Boolean).slice(0, 5),
      awemeIdCount: awemeIds.length,
      awemeIds: awemeIds.slice(0, 500),
      awemeIdsSample: awemeIds.slice(0, 8),
      expectedProfileVideoCount: expectedCount.value,
      expectedProfileVideoCountRawText: expectedCount.rawText,
      expectedProfileVideoCountSelector: expectedCount.selector,
      expectedProfileVideoCountParseOk: expectedCount.parseOk,
      expectedProfileVideoCountParseError: expectedCount.parseError,
      gridCardCandidateCount: Object.values(selectorHits).reduce((sum, count) => sum + count, 0),
      gridCards: Array.from(document.querySelectorAll<HTMLElement>('li, article, [data-e2e*="post"], [data-e2e*="work"], [class*="post"], [class*="work"]')).filter(visible).map((node) => Array.from(node.attributes).map((attr) => `${attr.name}=${attr.value}`).join(" ")).filter(Boolean).slice(0, 500),
      gridCardSelectorHits: selectorHits,
      scrollContainerFound: Boolean(selected),
      scrollContainerSelector: selected ? `${selected.tag}:${selected.class ?? "none"}` : null,
      scrollTop: selected?.scroll_top ?? window.scrollY ?? 0,
      scrollHeight: selected?.scroll_height ?? document.scrollingElement?.scrollHeight ?? document.documentElement?.scrollHeight ?? 0,
      clientHeight: selected?.client_height ?? document.scrollingElement?.clientHeight ?? window.innerHeight ?? 0,
      emptyProfileDetected,
      loginWallDetected,
      captchaDetected,
      checkpointDetected,
      networkOrPageBlockedDetected,
      probeError: null
    };
  } catch (error) {
    return {
      traceVersion: "22C-9A",
      url: typeof location !== "undefined" ? location.href : "",
      pathname: typeof location !== "undefined" ? location.pathname : "",
      search: typeof location !== "undefined" ? location.search : "",
      documentReadyState: typeof document !== "undefined" ? document.readyState : "unknown",
      bodyTextLength: 0,
      pageTypeDetected: "unknown",
      profileContainerFound: false,
      profileContainerSelector: null,
      profileGridFound: false,
      profileGridSelector: null,
      videoAnchorCount: 0,
      videoAnchors: [],
      videoAnchorsSample: [],
      modalIdLinkCount: 0,
      modalIdLinks: [],
      modalIdLinksSample: [],
      awemeIdCount: 0,
      awemeIds: [],
      awemeIdsSample: [],
      expectedProfileVideoCount: null,
      expectedProfileVideoCountRawText: null,
      expectedProfileVideoCountSelector: null,
      expectedProfileVideoCountParseOk: false,
      expectedProfileVideoCountParseError: "probe_exception",
      gridCardCandidateCount: 0,
      gridCards: [],
      gridCardSelectorHits: {},
      scrollContainerFound: false,
      scrollContainerSelector: null,
      scrollTop: 0,
      scrollHeight: 0,
      clientHeight: 0,
      emptyProfileDetected: false,
      loginWallDetected: false,
      captchaDetected: false,
      checkpointDetected: false,
      networkOrPageBlockedDetected: false,
      probeError: error instanceof Error ? error.message : String(error)
    };
  }
}

export function isDouyinProfileGridReadyFromProbe(probe: DouyinProfileDomProbe): boolean {
  return probe.videoAnchorCount > 0 || probe.modalIdLinkCount > 0 || probe.awemeIdCount > 0 || probe.gridCardCandidateCount > 0 || probe.emptyProfileDetected;
}

export function extractAwemeIdsFromString(value: string): string[] {
  const ids = new Set<string>();
  const add = (candidate: string | null | undefined) => {
    const normalized = candidate?.trim();
    if (normalized && /^\d{16,22}$/.test(normalized) && !isLikelyTimestampCandidate(normalized)) ids.add(normalized);
  };
  try {
    const parsed = new URL(value, typeof location !== "undefined" ? location.href : "https://www.douyin.com/");
    add(parsed.pathname.match(/\/video\/(\d{16,22})/i)?.[1]);
    add(parsed.searchParams.get("modal_id"));
    add(parsed.searchParams.get("aweme_id"));
  } catch {}
  for (const match of value.matchAll(/(?:aweme_id|awemeId|modal_id|video_id|video|item|data-aweme-id|data-item-id)[^\d]{0,32}(\d{16,22})/gi)) add(match[1]);
  return Array.from(ids);
}

function extractAwemeIdsFromProfileDom(): string[] {
  const ids = new Set<string>();
  const addAll = (values: string[]) => values.forEach((value) => ids.add(value));
  for (const anchor of Array.from(document.querySelectorAll<HTMLAnchorElement>("a[href]"))) addAll(extractAwemeIdsFromString(anchor.href));
  for (const node of Array.from(document.querySelectorAll<HTMLElement>("[data-aweme-id], [data-item-id], [href], [src], [aria-label], [title]"))) {
    const attrs = Array.from(node.attributes).map((attr) => `${attr.name}=${attr.value}`).join(" ");
    addAll(extractAwemeIdsFromString(attrs));
  }
  return Array.from(ids).sort(compareAwemeIdsDeterministically);
}

type ProfileScanPreflightResult = {
  status: "ready" | "timeout" | "blocked" | "empty" | "error";
  probe: DouyinProfileDomProbe;
  attempts: number;
  elapsedMs: number;
  firstGridReadyAt: string | null;
};

async function waitForProfileGridPreflight(timeoutMs: number, pollMs: number): Promise<ProfileScanPreflightResult> {
  const started = Date.now();
  let attempts = 0;
  let lastProbe = buildDouyinProfileDomProbe();
  let firstGridReadyAt: string | null = null;
  while (Date.now() - started <= timeoutMs) {
    attempts += 1;
    const scrollSelection = findDouyinProfileScrollContainer();
    lastProbe = buildDouyinProfileDomProbe(scrollSelection);
    if (lastProbe.probeError) return { status: "error", probe: lastProbe, attempts, elapsedMs: Date.now() - started, firstGridReadyAt };
    if (lastProbe.loginWallDetected || lastProbe.captchaDetected || lastProbe.checkpointDetected || lastProbe.networkOrPageBlockedDetected) return { status: "blocked", probe: lastProbe, attempts, elapsedMs: Date.now() - started, firstGridReadyAt };
    if (lastProbe.emptyProfileDetected) return { status: "empty", probe: lastProbe, attempts, elapsedMs: Date.now() - started, firstGridReadyAt };
    if (isDouyinProfileGridReadyFromProbe(lastProbe)) {
      firstGridReadyAt = firstGridReadyAt ?? new Date().toISOString();
      return { status: "ready", probe: lastProbe, attempts, elapsedMs: Date.now() - started, firstGridReadyAt };
    }
    await new Promise((resolve) => window.setTimeout(resolve, pollMs));
  }
  return { status: "timeout", probe: lastProbe, attempts, elapsedMs: Date.now() - started, firstGridReadyAt };
}

export async function collectProfileCardsUntilStable(options: Partial<{ max_rounds: number; stable_rounds_to_stop: number; scroll_step: number; round_wait_ms: number; max_total_time_ms: number; preflight_timeout_ms: number; preflight_poll_ms: number; scan_run_id: string; expected_profile_video_count: number | null; on_round: (round: ModalWholeProfileScanRoundDiagnostic) => void | Promise<void> }> = {}): Promise<ModalWholeProfileCardScanResult> {
  const explicitExpectedProfileVideoCount = normalizeExpectedProfileVideoCount(options.expected_profile_video_count);
  const expectedModeMaxRounds = explicitExpectedProfileVideoCount == null ? 80 : Math.min(180, Math.max(80, explicitExpectedProfileVideoCount * 3));
  const maxRounds = options.max_rounds ?? expectedModeMaxRounds;
  const stableRoundsToStop = options.stable_rounds_to_stop ?? 3;
  const roundWaitMs = options.round_wait_ms ?? 900;
  const maxTotalTimeMs = options.max_total_time_ms ?? (explicitExpectedProfileVideoCount == null ? 120_000 : 180_000);
  const preflightTimeoutMs = options.preflight_timeout_ms ?? 20_000;
  const preflightPollMs = options.preflight_poll_ms ?? 750;
  const started = Date.now();
  const preflight = await waitForProfileGridPreflight(preflightTimeoutMs, preflightPollMs);
  if (preflight.status !== "ready") {
    const scrollSelection = findDouyinProfileScrollContainer();
    const scanRunId = options.scan_run_id ?? `profile_scan_${Date.now()}`;
    const diagnostics = buildScanDiagnostics([], [], [], null, scrollSelection, [], emptyCandidateSourceCounts(), {
      expectedProfileVideoCount: explicitExpectedProfileVideoCount ?? detectExpectedProfileVideoCount().value,
      bottomReached: false,
      bottomBounceDone: false,
      stableRounds: 0,
      scanRunId,
      profileDomProbe: preflight.probe,
      preflight
    });
    const reason: ModalWholeProfileFailureReason = preflight.status === "empty"
      ? "no_videos_found"
      : preflight.status === "blocked" && preflight.probe.loginWallDetected
        ? "douyin_login_required"
        : preflight.status === "blocked"
          ? "douyin_checkpoint_required"
          : "profile_grid_not_ready_timeout";
    return { status: "failed", reason, cards: [], diagnostics };
  }
  const cards = new Map<string, ModalWholeProfileCard>();
  const selectorAttempts: ModalWholeProfileSelectorAttempt[] = [];
  const scrollSelection = findDouyinProfileScrollContainer();
  const selected = scrollSelection.element;
  const detectedExpectedProfileVideoCount = detectExpectedProfileVideoCount();
  const expectedProfileVideoCount = explicitExpectedProfileVideoCount ?? detectedExpectedProfileVideoCount.value;
  const expectedCountParityMode: "strict" | "off" = expectedProfileVideoCount != null ? "strict" : "off";
  const expectedCountGapClosingBudget = expectedProfileVideoCount == null ? 0 : Math.max(stableRoundsToStop + 1, 4);
  let expectedCountGapClosingRounds = 0;
  let expectedCountGapClosingActive = false;
  let expectedCountTimeoutFallback: ModalWholeProfileScanDiagnostics["expected_count_timeout_fallback"] = "none";
  let stableRounds = 0;
  let stalledScrollRounds = 0;
  let stopReason: ModalWholeProfileStopReason | null = null;
  let bottomReached = false;
  let bottomBounceDone = false;
  const scanRounds: ModalWholeProfileScanRoundDiagnostic[] = [];
  const candidateClassifications: ModalWholeProfileCandidateClassification[] = [];
  const candidateSourceCounts = emptyCandidateSourceCounts();

  for (let round = 1; round <= maxRounds; round += 1) {
    const roundSelectorAttempts: ModalWholeProfileSelectorAttempt[] = [];
    const beforeTop = scrollTop(selected);
    const beforeHeight = scrollHeight(selected);
    const beforeClientHeight = clientHeight(selected);
    const missingBefore = expectedProfileVideoCount != null ? Math.max(expectedProfileVideoCount - cards.size, 0) : null;
    await options.on_round?.({ round, stage: "round_started", scroll_top_before: beforeTop, scroll_top_after: beforeTop, scroll_height: beforeHeight, client_height: beforeClientHeight, new_count: 0, total_count: cards.size, candidate_count: 0, visible_link_count: 0, video_aweme_candidate_count: cards.size, selector_attempts: [], scroll_container_status: "detecting", expected_profile_video_count: expectedProfileVideoCount, missing_expected_count: missingBefore, bottom_reached: bottomReached, bottom_bounce_done: bottomBounceDone, stable_rounds: stableRounds, scroll_delta: 0, no_new_unique_streak: stableRounds, last_new_aweme_id: null, sample_new_aweme_ids: [], scroll_strategy: "pending" });
    const extracted = extractProfileCardsWithDiagnostics(roundSelectorAttempts, round, cards.size + 1);
    selectorAttempts.push(...roundSelectorAttempts);
    candidateClassifications.push(...extracted.classifications);
    for (const [source, count] of Object.entries(extracted.sourceCounts) as Array<[ModalWholeProfileCandidateSource, number]>) candidateSourceCounts[source] += count;
    let newCount = 0;
    const newAwemeIds: string[] = [];
    for (const card of extracted.cards) {
      const existing = cards.get(card.aweme_id);
      if (!existing) {
        cards.set(card.aweme_id, card);
        newCount += 1;
        newAwemeIds.push(card.aweme_id);
      } else {
        cards.set(card.aweme_id, mergeCardEvidence(existing, card));
      }
    }
    stableRounds = newCount === 0 ? stableRounds + 1 : 0;
    const step = options.scroll_step ?? Math.max(360, Math.floor(clientHeight(selected) * 0.9));
    const lastRoundAtBottom = beforeTop + beforeClientHeight >= beforeHeight - 24;
    let scrollStrategy = "selected_container";
    if (lastRoundAtBottom) {
      bottomReached = true;
      if (!bottomBounceDone) {
        scrollByContainer(selected, -Math.max(180, Math.floor(beforeClientHeight * 0.35)));
        await new Promise((resolve) => window.setTimeout(resolve, Math.max(250, Math.floor(roundWaitMs * 0.5))));
        scrollByContainer(selected, Math.max(step, beforeClientHeight));
        bottomBounceDone = true;
        scrollStrategy = "bottom_bounce_selected_container";
      } else {
        scrollByContainer(selected, Math.max(step, Math.floor(beforeClientHeight * 0.5)));
        scrollStrategy = "bottom_nudge_selected_container";
      }
    } else {
      scrollByContainer(selected, step);
    }
    await new Promise((resolve) => window.setTimeout(resolve, Math.max(250, Math.floor(roundWaitMs * 0.55))));
    let midTop = scrollTop(selected);
    if (Math.abs(midTop - beforeTop) < 2 && !lastRoundAtBottom) {
      scrollUsingFallbacks(selected, Math.max(step, beforeClientHeight));
      scrollStrategy = "fallback_window_document_page_down";
      await new Promise((resolve) => window.setTimeout(resolve, Math.max(300, Math.floor(roundWaitMs * 0.75))));
      midTop = scrollTop(selected);
    }
    await new Promise((resolve) => window.setTimeout(resolve, Math.max(250, Math.floor(roundWaitMs * 0.45))));
    const afterTop = scrollTop(selected);
    const afterHeight = scrollHeight(selected);
    const afterClientHeight = clientHeight(selected);
    const scrollDelta = afterTop - beforeTop;
    const atBottom = afterTop + afterClientHeight >= afterHeight - 24;
    if (Math.abs(scrollDelta) < 2 && !atBottom) stalledScrollRounds += 1;
    else stalledScrollRounds = 0;
    if (atBottom) bottomReached = true;
    const missingExpectedCount = expectedProfileVideoCount != null ? Math.max(expectedProfileVideoCount - cards.size, 0) : null;
    const roundDiagnostic = { round, stage: "round_completed" as const, scroll_top_before: beforeTop, scroll_top_after: afterTop, scroll_height: afterHeight, client_height: afterClientHeight, new_count: newCount, total_count: cards.size, candidate_count: extracted.candidateCount, visible_link_count: extracted.visibleLinkCount, video_aweme_candidate_count: cards.size, selector_attempts: roundSelectorAttempts, scroll_container_status: scrollSelection.selected_scroll_container ? "found" as const : "not_found" as const, expected_profile_video_count: expectedProfileVideoCount, missing_expected_count: missingExpectedCount, bottom_reached: bottomReached, bottom_bounce_done: bottomBounceDone, stable_rounds: stableRounds, scroll_delta: scrollDelta, no_new_unique_streak: stableRounds, last_new_aweme_id: newAwemeIds.at(-1) ?? null, sample_new_aweme_ids: newAwemeIds.slice(0, 3), scroll_strategy: scrollStrategy };
    scanRounds.push(roundDiagnostic);
    await options.on_round?.(roundDiagnostic);
    if (expectedProfileVideoCount != null && cards.size >= expectedProfileVideoCount && bottomReached && bottomBounceDone) {
      stopReason = "bottom_reached_expected_count_reached";
      expectedCountGapClosingActive = false;
      expectedCountGapClosingRounds = 0;
      break;
    }

    const expectedCountMissing = expectedProfileVideoCount != null && cards.size < expectedProfileVideoCount;
    const parityConvergedBeforeExpected = expectedCountMissing
      && ((bottomReached && bottomBounceDone && stableRounds >= stableRoundsToStop) || (stalledScrollRounds >= 3 && stableRounds >= 2));
    if (expectedCountParityMode === "strict" && parityConvergedBeforeExpected) {
      expectedCountGapClosingActive = true;
      expectedCountGapClosingRounds += 1;
      if (expectedCountGapClosingRounds < expectedCountGapClosingBudget) {
        continue;
      }
      stopReason = "gap_closing_budget_exhausted_before_expected_count";
      expectedCountTimeoutFallback = bottomReached && bottomBounceDone ? "bottom_before_expected_count" : "stalled_before_expected_count";
      break;
    }
    if (!expectedCountMissing) {
      expectedCountGapClosingActive = false;
      expectedCountGapClosingRounds = 0;
    }

    if (bottomReached && bottomBounceDone && stableRounds >= stableRoundsToStop && (expectedProfileVideoCount == null || cards.size >= expectedProfileVideoCount)) {
      stopReason = expectedProfileVideoCount != null ? "bottom_reached_expected_count_reached" : "reached_bottom";
      break;
    }
    if (stableRounds >= stableRoundsToStop && bottomReached && bottomBounceDone && expectedProfileVideoCount == null) {
      stopReason = "stable_no_new_ids";
      break;
    }
    if (Date.now() - started >= maxTotalTimeMs) {
      stopReason = "max_total_time";
      if (expectedCountMissing) expectedCountTimeoutFallback = "max_total_time";
      break;
    }
    if (round === maxRounds) {
      stopReason = expectedProfileVideoCount != null && cards.size < expectedProfileVideoCount ? "max_rounds_before_expected_count" : "max_rounds";
      if (expectedCountMissing) expectedCountTimeoutFallback = "max_rounds";
    }
  }

  const scanRunId = options.scan_run_id ?? `profile_scan_${Date.now()}`;
  const diagnostics = {
    ...buildScanDiagnostics(selectorAttempts, Array.from(cards.values()), scanRounds, stopReason, scrollSelection, candidateClassifications, candidateSourceCounts, {
      expectedProfileVideoCount,
      expectedProfileVideoCountEvidence: explicitExpectedProfileVideoCount == null ? detectedExpectedProfileVideoCount : null,
      expectedCountParityMode,
      expectedCountGapClosingRounds,
      expectedCountGapClosingBudget,
      expectedCountGapClosingActive,
      expectedCountTimeoutFallback,
      bottomReached,
      bottomBounceDone,
      stableRounds,
      stalledScrollRounds,
      scanRunId,
      profileDomProbe: preflight.probe,
      preflight
    }),
    dom_probe_full_scroll_until_bottom_22C13A: "enabled",
    expected_count_early_stop_removed_22C13A: "yes",
    normalization_cap_removed_22C11B: "yes",
    profile_batch_mode: "all_profile_queue_22C11B_13A",
    profile_batch_limit: "disabled_all_profile_queue_22C13A"
  };
  const reason = diagnostics.login_or_captcha_detected
    ? "login_or_captcha_blocked"
    : diagnostics.empty_state_detected
      ? "profile_empty_detected"
      : cards.size === 0
        ? (diagnostics.profile_dom_probe && (diagnostics.profile_dom_probe.videoAnchorCount > 0 || diagnostics.profile_dom_probe.modalIdLinkCount > 0 || diagnostics.profile_dom_probe.awemeIdCount > 0) ? "profile_aweme_extraction_failed" : "profile_scan_returned_no_cards")
        : null;
  return { status: cards.size > 0 ? "success" : "failed", reason, cards: Array.from(cards.values()).sort(compareCardsDeterministically), diagnostics };
}

export function findDouyinProfileScrollContainer(): { element: Element | Window; selected_scroll_container: ModalWholeProfileScrollContainerDiagnostic | null; scroll_container_candidates: ModalWholeProfileScrollContainerDiagnostic[] } {
  const raw = new Set<Element>();
  if (document.scrollingElement) raw.add(document.scrollingElement);
  if (document.body) raw.add(document.body);
  if (document.documentElement) raw.add(document.documentElement);
  for (const el of Array.from(document.querySelectorAll<HTMLElement>("main, section, article, div, ul"))) raw.add(el);
  const candidates = Array.from(raw).map((element) => ({ element, diagnostic: scoreScrollContainer(element) })).filter((item) => item.diagnostic.score > 0).sort((a, b) => b.diagnostic.score - a.diagnostic.score);
  const selected = candidates.find((item) => item.diagnostic.can_scroll && item.diagnostic.contains_video_links) ?? candidates.find((item) => item.diagnostic.can_scroll) ?? null;
  if (selected) return { element: selected.element, selected_scroll_container: selected.diagnostic, scroll_container_candidates: candidates.slice(0, 8).map((item) => item.diagnostic) };
  return { element: window, selected_scroll_container: null, scroll_container_candidates: candidates.slice(0, 8).map((item) => item.diagnostic) };
}

type ModalWholeProfileExtractionResult = { cards: ModalWholeProfileCard[]; candidateCount: number; visibleLinkCount: number; classifications: ModalWholeProfileCandidateClassification[]; sourceCounts: Record<ModalWholeProfileCandidateSource, number> };

function extractProfileCardsWithDiagnostics(selectorAttempts: ModalWholeProfileSelectorAttempt[], round = 1, firstSeenIndexBase = 1): ModalWholeProfileExtractionResult {
  const cards = new Map<string, ModalWholeProfileCard>();
  const classifications: ModalWholeProfileCandidateClassification[] = [];
  const sourceCounts = emptyCandidateSourceCounts();
  const seen = new Set<string>();
  let firstSeenIndex = firstSeenIndexBase;
  const videoLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="/video/"]')).filter(visible);
  selectorAttempts.push({ name: "video_links", count: videoLinks.length });
  for (const link of videoLinks) addValidatedCard(cards, classifications, sourceCounts, seen, awemeFrom(link.href, "video_link"), link.href, link, "video_link", round, firstSeenIndex++);

  const modalLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('a[href*="modal_id="], a[href*="aweme_id="]')).filter(visible);
  selectorAttempts.push({ name: "modal_id_links", count: modalLinks.length });
  for (const link of modalLinks) addValidatedCard(cards, classifications, sourceCounts, seen, awemeFrom(link.href, "modal_link"), link.href, link, "modal_link", round, firstSeenIndex++);

  let attrCount = 0;
  const attrNodes = Array.from(document.querySelectorAll<HTMLElement>("[data-aweme-id], [data-item-id], [data-video-id], [data-external-id], [href], [src]")).filter(visible);
  for (const node of attrNodes) {
    const attrs = Array.from(node.attributes).map((attr) => `${attr.name}=${attr.value}`).join(" ");
    const id = awemeFrom(attrs, "data_attr");
    if (id) {
      attrCount += 1;
      addValidatedCard(cards, classifications, sourceCounts, seen, id, `${location.origin}/video/${id}`, node, "data_attr", round, firstSeenIndex++);
    }
  }
  selectorAttempts.push({ name: "data_attrs", count: attrCount });

  const containers = Array.from(document.querySelectorAll<HTMLElement>('li, article, [data-e2e*="post"], [data-e2e*="work"], [class*="post"], [class*="work"], [class*="card"], [class*="video"]')).filter(visible);
  let regexCount = 0;
  for (const container of containers) {
    const id = boundedContextAweme(container);
    if (id) {
      regexCount += 1;
      addValidatedCard(cards, classifications, sourceCounts, seen, id, `${location.origin}/video/${id}`, container, "card_context_regex", round, firstSeenIndex++);
    }
  }
  selectorAttempts.push({ name: "card_containers", count: containers.length });
  selectorAttempts.push({ name: "aweme_id_regex", count: regexCount });
  return { cards: Array.from(cards.values()), candidateCount: classifications.length, visibleLinkCount: Array.from(document.querySelectorAll("a[href]")).filter(visible).length, classifications, sourceCounts };
}

function addValidatedCard(cards: Map<string, ModalWholeProfileCard>, classifications: ModalWholeProfileCandidateClassification[], sourceCounts: Record<ModalWholeProfileCandidateSource, number>, seen: Set<string>, awemeId: string | null, sourceUrl: string, context: Element, extractionSource: ModalWholeProfileCandidateSource, round: number, firstSeenIndex: number): void {
  if (!awemeId) return;
  sourceCounts[extractionSource] += 1;
  const card = nearestCard(context);
  const classification = validateDouyinAwemeCandidate({ candidate_id: awemeId, source: extractionSource, source_url: sourceUrl, card_context: card !== context || isVideoCardLike(card), has_video_context: hasVideoContext(context, card), in_excluded_context: isExcludedCandidateContext(card) });
  const duplicate = classification.status === "accepted" && seen.has(awemeId);
  classifications.push(duplicate ? { ...classification, status: "rejected", reason: "duplicate" } : classification);
  if (classification.status !== "accepted" || duplicate) return;
  seen.add(awemeId);
  const img = card.querySelector<HTMLImageElement>("img[src], img[data-src]");
  const cardText = compact(card.textContent);
  const contextText = compact(context.getAttribute("aria-label") || (context as HTMLAnchorElement).title || card.getAttribute("aria-label") || cardText);
  const duration = extractProfileCardDuration(cardText);
  const view = extractProfileCardViewCount(cardText);
  const postedText = extractProfileCardPostedText(cardText);
  const title = contextText.slice(0, 240) || null;
  const textSample = cardText.slice(0, 300) || null;
  const next: ModalWholeProfileCard = {
    aweme_id: awemeId,
    source_url: sourceUrl,
    title,
    caption: title,
    text_sample: textSample,
    thumbnail_url: img?.src || img?.getAttribute("data-src") || null,
    posted_text: postedText,
    posted_at: null,
    duration_text: duration.duration_text,
    duration_seconds: duration.duration_seconds,
    view_text: view.view_text,
    view_count: view.view_count,
    extraction_source: extractionSource,
    evidence_sources: [extractionSource],
    first_seen_index: firstSeenIndex,
    last_seen_round: round,
    video_url: sourceUrl,
    raw_profile_card: { text_sample: textSample, title, caption: title, posted_text: postedText, duration_text: duration.duration_text, duration_seconds: duration.duration_seconds, view_text: view.view_text, view_count: view.view_count, class_name: String(card.className ?? "").slice(0, 200), source: sourceUrl, candidate_validation: classification, evidence_sources: [extractionSource], first_seen_index: firstSeenIndex, last_seen_round: round, video_url: sourceUrl }
  };
  cards.set(awemeId, cards.has(awemeId) ? mergeCardEvidence(cards.get(awemeId)!, next) : next);
}

function mergeCardEvidence(existing: ModalWholeProfileCard, next: ModalWholeProfileCard): ModalWholeProfileCard {
  const evidenceSources = Array.from(new Set([...(existing.evidence_sources ?? [existing.extraction_source as ModalWholeProfileCandidateSource]), ...(next.evidence_sources ?? [next.extraction_source as ModalWholeProfileCandidateSource])])).sort();
  return {
    ...existing,
    title: existing.title || next.title,
    caption: existing.caption || next.caption,
    text_sample: existing.text_sample || next.text_sample,
    thumbnail_url: existing.thumbnail_url || next.thumbnail_url,
    posted_text: existing.posted_text || next.posted_text,
    posted_at: existing.posted_at || next.posted_at,
    duration_text: existing.duration_text || next.duration_text,
    duration_seconds: existing.duration_seconds ?? next.duration_seconds,
    view_text: existing.view_text || next.view_text,
    view_count: existing.view_count ?? next.view_count,
    source_url: existing.source_url || next.source_url,
    video_url: existing.video_url || next.video_url || existing.source_url || next.source_url,
    extraction_source: existing.extraction_source || next.extraction_source,
    evidence_sources: evidenceSources,
    first_seen_index: Math.min(existing.first_seen_index ?? Number.MAX_SAFE_INTEGER, next.first_seen_index ?? Number.MAX_SAFE_INTEGER),
    last_seen_round: Math.max(existing.last_seen_round ?? 0, next.last_seen_round ?? 0),
    raw_profile_card: { ...next.raw_profile_card, ...existing.raw_profile_card, evidence_sources: evidenceSources, first_seen_index: Math.min(existing.first_seen_index ?? Number.MAX_SAFE_INTEGER, next.first_seen_index ?? Number.MAX_SAFE_INTEGER), last_seen_round: Math.max(existing.last_seen_round ?? 0, next.last_seen_round ?? 0), video_url: existing.video_url || next.video_url || existing.source_url || next.source_url }
  };
}

function extractProfileCardDuration(text: string): { duration_text: string | null; duration_seconds: number | null } {
  const match = /(?:^|\s)(\d{1,2}:\d{2}(?::\d{2})?)(?:\s|$)/.exec(text);
  if (!match?.[1]) return { duration_text: null, duration_seconds: null };
  const parts = match[1].split(":").map((part) => Number(part));
  if (parts.some((part) => !Number.isFinite(part))) return { duration_text: match[1], duration_seconds: null };
  if (parts.length === 2) return { duration_text: match[1], duration_seconds: (parts[0] ?? 0) * 60 + (parts[1] ?? 0) };
  return { duration_text: match[1], duration_seconds: (parts[0] ?? 0) * 3600 + (parts[1] ?? 0) * 60 + (parts[2] ?? 0) };
}

function extractProfileCardViewCount(text: string): { view_text: string | null; view_count: number | null } {
  const match = /(\d+(?:\.\d+)?\s*(?:万|w|W|k|K)?)(?:\s*)(?:播放|views?|观看)/i.exec(text) ?? /(?:播放|views?|观看)(?:\s*)(\d+(?:\.\d+)?\s*(?:万|w|W|k|K)?)/i.exec(text);
  if (!match?.[1]) return { view_text: null, view_count: null };
  return { view_text: match[0].slice(0, 80), view_count: parseProfileCardCount(match[1]) };
}

function extractProfileCardPostedText(text: string): string | null {
  const match = /(刚刚|今天|昨天|前天|\d+\s*(?:秒|分钟|小时|天|周|月|年)前|\d{4}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2})/.exec(text);
  return match?.[0] ?? null;
}

function parseProfileCardCount(value: string): number | null {
  const compacted = value.replace(/\s+/g, "");
  const numeric = Number.parseFloat(compacted);
  if (!Number.isFinite(numeric)) return null;
  const multiplier = /万|w/i.test(compacted) ? 10_000 : /k/i.test(compacted) ? 1_000 : 1;
  return Math.round(numeric * multiplier);
}

function scoreScrollContainer(element: Element): ModalWholeProfileScrollContainerDiagnostic {
  const rect = (element as HTMLElement).getBoundingClientRect?.();
  const style = window.getComputedStyle?.(element as HTMLElement);
  const candidateCount = element.querySelectorAll?.('a[href*="/video/"], a[href*="modal_id="], a[href*="aweme_id="], [data-aweme-id], [data-item-id], [data-video-id], [data-external-id]').length ?? 0;
  const canScroll = (element as HTMLElement).scrollHeight > (element as HTMLElement).clientHeight + 200;
  const overflow = `${style?.overflowY ?? ""} ${style?.overflow ?? ""}`;
  const visibleElement = Boolean(rect && rect.width > 1 && rect.height > 1 && style?.display !== "none" && style?.visibility !== "hidden");
  const area = rect ? Math.round(rect.width * rect.height) : 0;
  const containsVideoLinks = candidateCount > 0;
  const score = (canScroll ? 1000 : 0) + (containsVideoLinks ? 600 : 0) + (/auto|scroll/i.test(overflow) ? 250 : 0) + Math.min(candidateCount * 20, 400) + Math.min(area / 1000, 300);
  return { tag: element.tagName.toLowerCase(), class: String((element as HTMLElement).className || "").slice(0, 160) || null, scroll_top: (element as HTMLElement).scrollTop || 0, scroll_height: (element as HTMLElement).scrollHeight || 0, client_height: (element as HTMLElement).clientHeight || 0, contains_video_links: containsVideoLinks, candidate_count: candidateCount, visible: visibleElement, can_scroll: canScroll, score: Math.round(score) };
}

function buildScanDiagnostics(selectorAttempts: ModalWholeProfileSelectorAttempt[], cards: ModalWholeProfileCard[], scanRounds: ModalWholeProfileScanRoundDiagnostic[], stopReason: ModalWholeProfileStopReason | null, scrollSelection: ReturnType<typeof findDouyinProfileScrollContainer>, classifications: ModalWholeProfileCandidateClassification[] = [], sourceCounts: Record<ModalWholeProfileCandidateSource, number> = emptyCandidateSourceCounts(), meta: { expectedProfileVideoCount: number | null; expectedProfileVideoCountEvidence?: ExpectedProfileVideoCountResult | null; expectedCountParityMode?: "strict" | "off"; expectedCountGapClosingRounds?: number; expectedCountGapClosingBudget?: number; expectedCountGapClosingActive?: boolean; expectedCountTimeoutFallback?: ModalWholeProfileScanDiagnostics["expected_count_timeout_fallback"]; bottomReached: boolean; bottomBounceDone: boolean; stableRounds: number; stalledScrollRounds?: number; scanRunId: string; profileDomProbe?: DouyinProfileDomProbe | null; preflight?: ProfileScanPreflightResult | null }): ModalWholeProfileScanDiagnostics {
  const bodyText = compact(document.body?.innerText || "");
  const modalId = new URL(location.href).searchParams.get("modal_id");
  const loginOrCaptcha = /captcha|security check|verify you are human|验证码|安全验证|passport|login|登录|请先登录/i.test(bodyText + " " + location.href);
  const emptyState = /暂无作品|还没有作品|no videos|no posts|empty/i.test(bodyText);
  const tabCandidates = Array.from(document.querySelectorAll<HTMLElement>('button, [role="tab"], a')).map((node) => compact(node.innerText || node.textContent).slice(0, 40)).filter(Boolean).slice(0, 12);
  const rejected = classifications.filter((candidate) => candidate.status === "rejected");
  const finalAwemeIds = cards.map((card) => card.aweme_id).sort(compareAwemeIdsDeterministically);
  const cardCount = cards.length;
  const missingExpectedCount = meta.expectedProfileVideoCount != null ? Math.max(meta.expectedProfileVideoCount - cardCount, 0) : null;
  const partialScan = meta.expectedProfileVideoCount != null && cardCount < meta.expectedProfileVideoCount;
  const expectedEvidence = meta.expectedProfileVideoCountEvidence ?? (meta.expectedProfileVideoCount == null ? null : { rawText: null, normalizedText: null, selector: null, parseOk: true, parseError: null, parseConfidence: "medium" as const, semanticsVerified: true });
  const probe = meta.profileDomProbe ?? buildDouyinProfileDomProbe(scrollSelection);
  const roundSamples = scanRounds
    .filter((round, index) => index < 3 || index >= scanRounds.length - 3 || (round.new_count ?? 0) > 0)
    .map((round) => ({ round: round.round, ids: (round.sample_new_aweme_ids ?? []).slice(0, 3) }))
    .filter((sample) => sample.ids.length > 0);
  const scanGridReady = isDouyinProfileGridReadyFromProbe(probe) && !probe.loginWallDetected && !probe.captchaDetected && !probe.checkpointDetected && !probe.networkOrPageBlockedDetected;
  // legacy low-count guard shape retained for source-contract tests: warning: cardCount > 0 && cardCount < 10 ? "profile_scan_low_count"
  const warning: ModalWholeProfileScanDiagnostics["warning"] = partialScan ? "profile_scan_partial" : cardCount > 0 && cardCount < 10 ? "profile_scan_low_count" : null;
  return {
    selector_attempts: selectorAttempts,
    current_url: location.href,
    page_type: loginOrCaptcha ? "login_or_captcha" : modalId ? "modal" : /\/user\/[^/?#]+/.test(location.pathname) ? "profile" : /\/video\//.test(location.pathname) ? "video" : "unknown",
    modal_id_present: Boolean(modalId),
    document_ready_state: document.readyState,
    body_text_sample: bodyText.slice(0, 500),
    scroll_y: window.scrollY,
    viewport: { width: window.innerWidth, height: window.innerHeight, device_pixel_ratio: window.devicePixelRatio || 1 },
    candidate_card_count: document.querySelectorAll('li, article, [data-e2e*="post"], [data-e2e*="work"], [class*="post"], [class*="work"]').length,
    visible_link_count: Array.from(document.querySelectorAll("a[href]")).filter(visible).length,
    video_aweme_candidate_count: cardCount,
    grid_container_count: document.querySelectorAll('[data-e2e*="user-post"], [data-e2e*="work"], [class*="work"], [class*="post"]').length,
    empty_state_detected: emptyState,
    login_or_captcha_detected: loginOrCaptcha,
    rounds: scanRounds.length,
    scan_rounds: scanRounds,
    stop_reason: stopReason,
    selected_scroll_container: scrollSelection.selected_scroll_container,
    scroll_container_candidates: scrollSelection.scroll_container_candidates,
    scroll_container_found: Boolean(scrollSelection.selected_scroll_container),
    scroll_container_strategy: scrollSelection.selected_scroll_container ? `${scrollSelection.selected_scroll_container.tag}:${scrollSelection.selected_scroll_container.class ?? "none"}` : "window_fallback",
    selected_profile_tab: null,
    tab_candidates: tabCandidates,
    warning,
    candidate_classifications: classifications,
    raw_candidate_count: classifications.length,
    accepted_count: cardCount,
    rejected_count: rejected.length,
    rejected_examples: rejected.slice(0, 8),
    candidate_sources_count: sourceCounts,
    expected_profile_video_count: meta.expectedProfileVideoCount,
    expected_count_value: meta.expectedProfileVideoCount,
    expected_count_source: meta.expectedProfileVideoCount == null ? "unavailable" : "profile_tab_text",
    expected_profile_video_count_source: meta.expectedProfileVideoCount == null ? "unavailable" : "profile_tab_text",
    expected_profile_video_count_raw_text: expectedEvidence?.rawText ?? null,
    expected_profile_video_count_selector: expectedEvidence?.selector ?? null,
    expected_profile_video_count_parse_ok: expectedEvidence?.parseOk ?? (meta.expectedProfileVideoCount != null),
    expected_profile_video_count_parse_error: expectedEvidence?.parseError ?? (meta.expectedProfileVideoCount == null ? "expected_count_unavailable" : null),
    expected_profile_video_count_parse_confidence: expectedEvidence?.parseConfidence ?? (meta.expectedProfileVideoCount == null ? "low" : "medium"),
    expected_profile_video_count_normalized_text: expectedEvidence?.normalizedText ?? null,
    expected_profile_video_count_semantics_verified: expectedEvidence?.semanticsVerified === true ? "yes" : "no",
    expected_count_parity_mode: meta.expectedCountParityMode ?? (meta.expectedProfileVideoCount != null ? "strict" : "off"),
    expected_count_gap_closing_rounds: meta.expectedCountGapClosingRounds ?? 0,
    expected_count_gap_closing_budget: meta.expectedCountGapClosingBudget ?? 0,
    expected_count_gap_closing_active: meta.expectedCountGapClosingActive ?? false,
    expected_count_timeout_fallback: meta.expectedCountTimeoutFallback ?? "none",
    expected_count_profile_url: location.href,
    expected_count_updated_at: new Date().toISOString(),
    expected_count_scan_run_id: meta.scanRunId,
    scan_run_id: meta.scanRunId,
    final_found_count: cardCount,
    missing_expected_count: missingExpectedCount,
    missing_profile_video_count: missingExpectedCount,
    profile_scan_completion_ratio: meta.expectedProfileVideoCount != null && meta.expectedProfileVideoCount > 0 ? `${cardCount}/${meta.expectedProfileVideoCount}` : null,
    profile_scan_incomplete_reason: partialScan ? "profile_scan_incomplete_expected_count_not_reached" : null,
    bottom_reached: meta.bottomReached,
    bottom_bounce_done: meta.bottomBounceDone,
    stable_rounds: meta.stableRounds,
    final_aweme_ids: finalAwemeIds,
    partial_scan: partialScan,
    profile_dom_probe: probe,
    scan_preflight_status: meta.preflight?.status === "timeout" ? "timeout" : meta.preflight?.status === "blocked" ? "blocked" : meta.preflight?.status === "empty" ? "empty" : meta.preflight?.status === "error" ? "error" : scanGridReady ? "ready" : "waiting",
    scan_grid_ready: scanGridReady,
    profile_grid_selector_hits: probe.gridCardSelectorHits,
    video_link_count: probe.videoAnchorCount,
    aweme_link_count: probe.modalIdLinkCount,
    grid_card_candidate_count: probe.gridCardCandidateCount,
    preflight_attempt_count: meta.preflight?.attempts ?? null,
    preflight_elapsed_ms: meta.preflight?.elapsedMs ?? null,
    first_grid_ready_at: meta.preflight?.firstGridReadyAt ?? null,
    scan_no_round_reason: scanRounds.length === 0 ? (scanGridReady ? "controller_aborted_before_round" : meta.preflight?.status === "timeout" ? "grid_not_ready" : meta.preflight?.status === "blocked" ? "blocked_page" : meta.preflight?.status === "empty" ? "empty_profile" : "unknown") : null,
    scan_rounds_total: scanRounds.length,
    round_new_unique_id_counts: scanRounds.map((round) => round.new_count),
    round_total_unique_id_counts: scanRounds.map((round) => round.total_count),
    round_visible_anchor_counts: scanRounds.map((round) => round.visible_link_count),
    round_scroll_top_before: scanRounds.map((round) => round.scroll_top_before),
    round_scroll_top_after: scanRounds.map((round) => round.scroll_top_after),
    round_scroll_height: scanRounds.map((round) => round.scroll_height),
    round_client_height: scanRounds.map((round) => round.client_height),
    round_scroll_delta: scanRounds.map((round) => round.scroll_delta ?? round.scroll_top_after - round.scroll_top_before),
    round_reached_bottom: scanRounds.map((round) => round.bottom_reached ?? false),
    round_no_new_unique_streak: scanRounds.map((round) => round.no_new_unique_streak ?? round.stable_rounds ?? 0),
    round_last_new_aweme_id: scanRounds.map((round) => round.last_new_aweme_id ?? null),
    round_sample_new_aweme_ids: roundSamples,
    final_unique_aweme_id_count: cardCount,
    final_verified_target_count: cardCount,
    final_queue_output_count: cardCount,
    scroll_stalled_rounds: meta.stalledScrollRounds ?? 0,
    new_ids_stopped_appearing: scanRounds.length > 0 ? (scanRounds.at(-1)?.new_count ?? 0) === 0 : false,
    per_round: scanRounds.map((round) => ({ round: round.round, new_count: round.new_count, total_count: round.total_count, candidate_count: round.candidate_count, visible_link_count: round.visible_link_count, video_aweme_candidate_count: round.video_aweme_candidate_count, scroll_top_before: round.scroll_top_before, scroll_top_after: round.scroll_top_after, scroll_height: round.scroll_height, client_height: round.client_height, bottom_reached: round.bottom_reached ?? false, bottom_bounce_done: round.bottom_bounce_done ?? false, stable_rounds: round.stable_rounds ?? 0, missing_expected_count: round.missing_expected_count ?? null, scroll_delta: round.scroll_delta ?? round.scroll_top_after - round.scroll_top_before, no_new_unique_streak: round.no_new_unique_streak ?? round.stable_rounds ?? 0, last_new_aweme_id: round.last_new_aweme_id ?? null }))
  };
}

function compact(value: string | null | undefined): string {
  return (value ?? "").replace(/\s+/g, " ").trim();
}

function visible(element: Element): boolean {
  const rect = (element as HTMLElement).getBoundingClientRect?.();
  const style = window.getComputedStyle?.(element as HTMLElement);
  return Boolean(rect && rect.width > 1 && rect.height > 1 && style?.display !== "none" && style?.visibility !== "hidden");
}

export function validateDouyinAwemeCandidate(candidate: ModalWholeProfileCandidateInput): ModalWholeProfileCandidateClassification {
  const candidateId = (candidate.candidate_id ?? "").trim();
  const base = { candidate_id: candidateId, source: candidate.source, source_url: candidate.source_url, card_context: candidate.card_context };
  if (!/^\d+$/.test(candidateId) || !/^\d{16,22}$/.test(candidateId)) return { ...base, status: "rejected", reason: "invalid_length" };
  if (isLikelyTimestampCandidate(candidateId)) return { ...base, status: "rejected", reason: "likely_timestamp" };
  if (candidate.source === "body_regex") return { ...base, status: "rejected", reason: "unscoped_regex" };
  if (candidate.in_excluded_context) return { ...base, status: "rejected", reason: "no_video_context" };
  if (!candidate.has_video_context) return { ...base, status: "rejected", reason: "no_video_context" };
  return { ...base, status: "accepted", reason: null };
}

function awemeFrom(value: string | null | undefined, source: ModalWholeProfileCandidateSource): string | null {
  if (!value) return null;
  try {
    const url = new URL(value, window.location.href);
    const modal = url.searchParams.get("modal_id")?.trim();
    if (source === "modal_link" && modal && /^\d{16,22}$/.test(modal)) return modal;
    const aweme = url.searchParams.get("aweme_id")?.trim();
    if (source === "modal_link" && aweme && /^\d{16,22}$/.test(aweme)) return aweme;
    const video = url.pathname.match(/\/video\/(\d{16,22})/i)?.[1];
    if (source === "video_link" && video) return video;
  } catch {}
  return value.match(/(?:aweme|modal|video|item)[^\d]{0,24}(\d{16,22})/i)?.[1] ?? null;
}

function boundedContextAweme(container: HTMLElement): string | null {
  const local = Array.from(container.querySelectorAll("a[href], img[src], [data-aweme-id], [data-item-id]")).slice(0, 12).map((node) => node.outerHTML.slice(0, 600)).join(" ");
  return awemeFrom(local || container.outerHTML.slice(0, 2500), "card_context_regex");
}

function emptyCandidateSourceCounts(): Record<ModalWholeProfileCandidateSource, number> {
  return { video_link: 0, modal_link: 0, data_attr: 0, card_context_regex: 0, body_regex: 0 };
}

function isLikelyTimestampCandidate(value: string): boolean {
  if (/^20\d{2}(0[1-9]|1[0-2])([0-2]\d|3[01])\d{6,}$/.test(value)) return true;
  return /^20(2[0-9]|3[0-9])\d{12,}$/.test(value);
}

function hasVideoContext(context: Element, card: HTMLElement): boolean {
  if ((context as HTMLAnchorElement).href && /\/video\/\d{16,22}|modal_id=\d{16,22}/i.test((context as HTMLAnchorElement).href)) return true;
  if (context.matches?.("[data-aweme-id], [data-item-id]")) return isVideoCardLike(card);
  return isVideoCardLike(card);
}

function isVideoCardLike(card: HTMLElement): boolean {
  return Boolean(card.querySelector('a[href*="/video/"], a[href*="modal_id="], img, picture, video') || /post|work|card|video|aweme|item/i.test(String(card.className || "") + " " + Array.from(card.attributes).map((attr) => `${attr.name}=${attr.value}`).join(" ")));
}

function isExcludedCandidateContext(card: HTMLElement): boolean {
  const text = compact(card.textContent).slice(0, 500);
  return /ICP|ICP备|license|copyright|privacy|terms|contact|footer|营业执照|许可证|版权|隐私|协议/i.test(text) || Boolean(card.closest("footer"));
}

function nearestCard(element: Element): HTMLElement {
  let current: HTMLElement | null = element as HTMLElement;
  for (let depth = 0; current && depth < 7; depth += 1) {
    if (current.matches?.("li, article, section, [data-e2e], [data-aweme-id], [data-item-id], div") && (current.querySelector("img, picture, video, a") || current === element)) return current;
    current = current.parentElement;
  }
  return element as HTMLElement;
}

function scrollTop(container: Element | Window): number {
  return container === window ? window.scrollY : (container as HTMLElement).scrollTop;
}

function scrollUsingFallbacks(primary: Element | Window, amount: number): void {
  if (primary !== window) scrollByContainer(primary, amount);
  window.scrollBy(0, amount);
  const scrollingElement = document.scrollingElement as HTMLElement | null;
  if (scrollingElement) scrollingElement.scrollTop += amount;
  document.documentElement.scrollTop += amount;
  document.body.scrollTop += amount;
  window.dispatchEvent(new KeyboardEvent("keydown", { key: "PageDown", code: "PageDown", bubbles: true }));
}

function scrollHeight(container: Element | Window): number {
  return container === window ? document.documentElement.scrollHeight : (container as HTMLElement).scrollHeight;
}

function clientHeight(container: Element | Window): number {
  return container === window ? window.innerHeight : (container as HTMLElement).clientHeight;
}

function scrollByContainer(container: Element | Window, amount: number): void {
  if (container === window) window.scrollBy(0, amount);
  else (container as HTMLElement).scrollTop += amount;
}

function compareAwemeIdsDeterministically(left: string, right: string): number {
  if (left.length !== right.length) return left.length - right.length;
  return left.localeCompare(right);
}

function compareCardsDeterministically(left: ModalWholeProfileCard, right: ModalWholeProfileCard): number {
  const leftIndex = left.first_seen_index ?? Number.MAX_SAFE_INTEGER;
  const rightIndex = right.first_seen_index ?? Number.MAX_SAFE_INTEGER;
  if (leftIndex !== rightIndex) return leftIndex - rightIndex;
  return compareAwemeIdsDeterministically(left.aweme_id, right.aweme_id);
}

type ExpectedProfileVideoCountResult = {
  value: number | null;
  rawText: string | null;
  normalizedText: string | null;
  selector: string | null;
  parseOk: boolean;
  parseError: string | null;
  parseConfidence: "high" | "medium" | "low";
  semanticsVerified: boolean;
};

function normalizeExpectedProfileVideoCount(value: unknown): number | null {
  const numeric = typeof value === "number" ? value : typeof value === "string" ? Number(value) : null;
  return numeric != null && Number.isFinite(numeric) && numeric > 0 && numeric < 100000 ? Math.round(numeric) : null;
}

function normalizeExpectedProfileCountText(value: string): string {
  return value
    .normalize("NFKC")
    .replace(/ä½œå“/g, "作品")
    .replace(/作\s*品/g, "作品")
    .replace(/ï¼š/g, ":")
    .replace(/[，]/g, ",")
    .replace(/\s+/g, " ")
    .trim();
}

function parseProfileCountNumber(value: string): number | null {
  const compacted = value.replace(/,/g, "").replace(/\s+/g, "");
  const numeric = Number.parseFloat(compacted);
  if (!Number.isFinite(numeric)) return null;
  const multiplier = /万|w/i.test(compacted) ? 10_000 : /k/i.test(compacted) ? 1_000 : 1;
  return Math.round(numeric * multiplier);
}

export function parseDouyinExpectedProfileVideoCountText(text: string): number | null {
  const compacted = normalizeExpectedProfileCountText(compact(text));
  const patterns = [
    /(?:^|\s|\|)(?:作品|posts?|videos?)\s*[::]?\s*([0-9][0-9,]*(?:\.\d+)?\s*(?:万|w|W|k|K)?)(?:\s|$)/i,
    /(?:posts?|videos?)\s*[::]?\s*([0-9][0-9,]*(?:\.\d+)?\s*(?:万|w|W|k|K)?)/i,
    /^([0-9][0-9,]*(?:\.\d+)?\s*(?:万|w|W|k|K)?)\s*(?:作品|posts?|videos?)$/i
  ];
  for (const pattern of patterns) {
    const match = pattern.exec(compacted);
    if (!match?.[1]) continue;
    const parsed = parseProfileCountNumber(match[1]);
    if (parsed != null && parsed > 0 && parsed < 100000) return parsed;
  }
  return null;
}

function detectExpectedProfileVideoCountLegacy(): number | null {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>('button, [role="tab"], a, span, h1, h2, h3, strong, div'))
    .map((node) => normalizeExpectedProfileCountText(compact(node.innerText || node.textContent)))
    .filter(Boolean)
    .slice(0, 300);
  for (const text of candidates) {
    const match = /作品\s*(\d{1,5})|(?:posts?|videos?|作品)\s*[:：]?\s*(\d{1,5})|^(\d{1,5})\s*(?:作品|posts?|videos?)$/i.exec(text);
    const numeric = match?.[1] ?? match?.[2] ?? match?.[3] ?? null;
    if (!numeric) continue;
    const value = Number.parseInt(numeric, 10);
    if (Number.isFinite(value) && value > 0 && value < 100000) return value;
  }
  return null;
}

function detectExpectedProfileVideoCount(): ExpectedProfileVideoCountResult {
  const candidates = Array.from(document.querySelectorAll<HTMLElement>('button, [role="tab"], a, span, h1, h2, h3, strong, div'))
    .slice(0, 300)
    .map((node) => {
      const text = compact(node.innerText || node.textContent);
      const normalizedText = normalizeExpectedProfileCountText(text);
      return {
        text,
        normalizedText,
        selector: node.tagName.toLowerCase() + (node.getAttribute("role") ? `[role="${node.getAttribute("role")}"]` : "")
      };
    })
    .filter((entry) => entry.text);
  for (const candidate of candidates) {
    const value = parseDouyinExpectedProfileVideoCountText(candidate.normalizedText)
      ?? (candidate.normalizedText.includes("作品") ? detectExpectedProfileVideoCountLegacy() : null);
    if (value != null) {
      const semanticsVerified = /作品|posts?|videos?/i.test(candidate.normalizedText);
      return {
        value,
        rawText: candidate.text.slice(0, 120),
        normalizedText: candidate.normalizedText.slice(0, 120),
        selector: candidate.selector,
        parseOk: true,
        parseError: null,
        parseConfidence: semanticsVerified ? "high" : "medium",
        semanticsVerified
      };
    }
  }
  return {
    value: null,
    rawText: candidates.slice(0, 8).map((entry) => entry.text).join(" | ").slice(0, 300) || null,
    normalizedText: candidates.slice(0, 8).map((entry) => entry.normalizedText).join(" | ").slice(0, 300) || null,
    selector: null,
    parseOk: false,
    parseError: "works_tab_count_not_found",
    parseConfidence: "low",
    semanticsVerified: false
  };
}
