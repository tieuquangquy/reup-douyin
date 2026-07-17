export type DouyinPageType =
  | "login_page"
  | "challenge_page"
  | "home_feed_page"
  | "profile_page"
  | "profile_feed_page"
  | "video_detail_page"
  | "unsupported_page"
  | "unknown_page";

export interface PageSnapshot {
  url: string | null;
  title: string | null;
  body_text_sample?: string | null;
  page_type: DouyinPageType;
  profile_url?: string | null;
  profile_external_id?: string | null;
  handle?: string | null;
  display_name?: string | null;
  video_link_count: number;
}

export type ThumbnailSource = "network_json" | "detail_hydrate" | "dom_fallback" | "missing";
export type ContextMismatchCode = "context_mismatch" | "session_mismatch" | "project_mismatch" | "profile_mismatch" | "tab_mismatch" | "page_mismatch";

export interface CaptureContext {
  capture_id?: string | null;
  tab_id?: number | null;
  page_url?: string | null;
  page_url_normalized?: string | null;
  profile_url?: string | null;
  profile_external_id?: string | null;
  captured_at?: string | null;
  cache_scope_key?: string | null;
}

export type ThumbnailMissingReason =
  | "network_cover_missing"
  | "detail_hydrate_not_run"
  | "detail_hydrate_no_cover"
  | "dom_cover_missing"
  | "backend_drop"
  | "api_drop"
  | "frontend_resolver_drop"
  | "thumbnail_unresolved";
export type PostedSource = "network_json" | "detail_hydrate" | "dom_text" | "fallback_none";
export type DurationSource = "network_json" | "detail_hydrate" | "dom_text" | "fallback_none";
export type MetricSource =
  | "network_json"
  | "detail_hydrate"
  | "dom_text"
  | "dom_zero_sentinel"
  | "dom_profile_card_fallback"
  | "calibrated_point_dom"
  | "calibrated_point_ocr"
  | "fallback_none";
export type EngagementRateSource = "derived_from_canonical_counts" | "fallback_none";

export type RawEvidenceValue = string | number | boolean | null | RawEvidenceValue[] | { [key: string]: RawEvidenceValue };
export type RawAwemeEvidence = Record<string, RawEvidenceValue>;

export interface RawDomSnapshot {
  aweme_id: string;
  visible_text: string | null;
  href: string | null;
  source_url: string | null;
  image_candidates: string[];
  data_attributes: Record<string, string>;
  local_text_snippets: string[];
}

export interface ActionRailIconCandidateDiagnostic {
  kind: "like" | "comment" | "favorite" | "share" | null;
  rect: ActionRailRectDiagnostic;
  accepted: boolean;
  reason: string | null;
  hints: string | null;
}

export interface ActionRailIconAnchoredMetricDiagnostic {
  metric: "like" | "comment" | "favorite" | "share";
  icon_rect: ActionRailRectDiagnostic;
  count_text: string | null;
  count_rect: ActionRailRectDiagnostic | null;
  distance_icon_to_count: number | null;
  source: "icon_anchored_right_rail";
}

export type ModalMetadataSourcePriority =
  | "accessibility_tree_right_rail"
  | "screenshot_ocr_right_rail"
  | "cdp_dom_snapshot_right_rail"
  | "cdp_network_aweme"
  | "cdp_runtime_aweme"
  | "page_network_cache_aweme"
  | "script_hydration_aweme"
  | "video_element_duration"
  | "exact_aweme_runtime_object"
  | "exact_aweme_script_hydration_object"
  | "exact_aweme_network_cache_object"
  | "combined_modal_text_fallback"
  | "visible_right_rail_fallback"
  | "missing";

export type ExactAwemeRuntimeSource = "cdp_network" | "cdp_runtime" | "react_fiber" | "react_props" | "vue_state" | "script_hydration" | "network_cache" | "none";

export interface CdpAwemeStatus {
  attached: boolean;
  tab_id: number | null;
  debugger_version?: string | null;
  network_enabled?: boolean;
  runtime_enabled?: boolean;
  response_count: number;
  json_response_count?: number;
  candidate_aweme_count: number;
  exact_match_count: number;
  runtime_exact_match_count?: number;
  last_matching_aweme_id?: string | null;
  last_matching_response_url: string | null;
  last_error: string | null;
}

export interface CdpAwemeEvidence {
  aweme_id: string;
  source_used: "cdp_network_aweme" | "cdp_runtime_aweme" | "page_network_cache_aweme" | "script_hydration_aweme";
  raw_aweme: RawAwemeEvidence;
  raw_aweme_keys: string[];
  duration_seconds: number | null;
  duration_text: string | null;
  view_count: number | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  posted_text: string | null;
  posted_text_raw?: string | null;
  posted_at: string | null;
  posted_display?: string | null;
  posted_parse_confidence?: string | null;
  response_url?: string | null;
}

export interface RawDomDetailMetrics {
  aweme_id?: string | null;
  target_aweme_id?: string | null;
  duration_seconds?: number | null;
  duration_text?: string | null;
  duration_text_conflict?: string | null;
  like_count?: number | null;
  like_count_text?: string | null;
  like_count_source?: string | null;
  comment_count?: number | null;
  comment_count_text?: string | null;
  comment_count_source?: string | null;
  favorite_count?: number | null;
  favorite_count_text?: string | null;
  favorite_count_source?: string | null;
  share_count?: number | null;
  share_count_text?: string | null;
  share_count_source?: string | null;
  view_count?: number | null;
  view_count_source?: string | null;
  posted_text?: string | null;
  posted_text_raw?: string | null;
  posted_at?: string | null;
  posted_display?: string | null;
  posted_source?: string | null;
  posted_parse_confidence?: string | null;
  selected_duration_source?: string | null;
  duration_text_source?: string | null;
  source_priority_used?: ModalMetadataSourcePriority;
  source_used?: string | null;
  exact_aweme_runtime_found?: boolean;
  exact_aweme_found?: boolean;
  exact_aweme_source?: ExactAwemeRuntimeSource;
  raw_aweme_keys?: string[] | null;
  fallback_used?: ModalMetadataSourcePriority | null;
  cdp_attached?: boolean;
  cdp_response_count?: number;
  cdp_json_response_count?: number;
  cdp_candidate_aweme_count?: number;
  cdp_exact_match_count?: number;
  runtime_exact_match_count?: number;
  last_matching_aweme_id?: string | null;
  last_matching_response_url?: string | null;
  cdp_last_error?: string | null;
  rejected_reason?: string | null;
  action_blocks_found?: number | null;
  modal_action_blocks_found?: number | null;
  like_block_text?: string | null;
  comment_block_text?: string | null;
  favorite_block_text?: string | null;
  share_block_text?: string | null;
  profile_card_like_text?: string | null;
  action_block_diagnostics?: ActionRailBlockDiagnostic[] | null;
  rail_region?: ActionRailRailRegionDiagnostic | null;
  numeric_labels_found?: ActionRailNumericLabelDiagnostic[] | null;
  selected_rail_labels?: string[] | null;
  selected_rail_labels_with_rect?: ActionRailNumericLabelDiagnostic[] | null;
  assigned_metrics?: ActionRailAssignedMetricDiagnostic[] | null;
  rejected_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  extraction_mode?: ActionRailExtractionMode | null;
  combined_text_segment?: string | null;
  combined_count_tokens?: string[] | null;
  rejected_candidates_count?: number | null;
  rejected_candidate_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  rail_x_band?: ActionRailXBandDiagnostic | null;
  computed_rail_x_band?: ActionRailXBandDiagnostic | null;
  viewport_width?: number | null;
  viewport_height?: number | null;
  active_video_rect?: ActionRailRectDiagnostic | null;
  modal_candidate_rect?: ActionRailRectDiagnostic | null;
  icon_candidates?: ActionRailIconCandidateDiagnostic[] | null;
  selected_action_icons?: ActionRailIconCandidateDiagnostic[] | null;
  icon_anchored_metrics?: ActionRailIconAnchoredMetricDiagnostic[] | null;
  rejected_number_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  rejected_icon_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  compact_count_candidates?: ActionRailCompactCountCandidateDiagnostic[] | null;
  compact_text_node_candidates_count?: number | null;
  compact_count_clusters?: ActionRailCompactCountClusterDiagnostic[] | null;
  selected_compact_count_cluster?: ActionRailCompactCountClusterDiagnostic | null;
  selected_cluster_texts?: string[] | null;
  selected_cluster_rects?: ActionRailRectDiagnostic[] | null;
  action_blocks_missing_reason?: ActionRailMissingReason | null;
  warning_reason?: string | null;
  assigned_metric_node_ids?: string[] | null;
  metric_confidence_by_field?: Record<string, string> | null;
  rejected_metric_reasons?: Record<string, string> | null;
  extraction_warning?: string | null;
  snapshot_text_count?: number | null;
  compact_labels_found?: number | null;
  right_rail_region?: ActionRailRailRegionDiagnostic | null;
  selected_snapshot_rail_labels?: CdpDomSnapshotRailLabel[] | null;
  accessibility_node_count?: number | null;
  accessibility_compact_labels?: VisualRightRailLabel[] | null;
  ocr_used?: boolean | null;
  ocr_raw_text?: string | null;
  ocr_selected_lines?: string[] | null;
  visual_extractor_diagnostics?: VisualRightRailDiagnostics | null;
  point_results?: Record<string, CalibratedPointMetricResult> | null;
  extraction_source:
    | "dom_detail_modal"
    | "calibrated_point_dom"
    | "calibrated_point_ocr"
    | "mixed_calibrated_point"
    | "accessibility_tree_right_rail"
    | "screenshot_ocr_right_rail"
    | "cdp_dom_snapshot_right_rail"
    | "cdp_network_aweme"
    | "cdp_runtime_aweme"
    | "page_network_cache_aweme"
    | "script_hydration_aweme"
    | "video_element_duration"
    | "exact_aweme_runtime_object"
    | "exact_aweme_script_hydration_object"
    | "exact_aweme_network_cache_object"
    | "combined_modal_text_fallback";
  confidence: "high";
}

export type CalibratedMetricName = "like_count" | "comment_count" | "favorite_count" | "share_count";

export type RightRailCalibrationPointName = CalibratedMetricName | "next_video_button";

export type FullModalHarvestNextPointStatus = "calibrated" | "missing";

export type FullModalHarvestNavigationResult = "clicked_next_point" | "arrow_down_fallback" | "page_down_fallback" | "wheel_fallback" | "modal_changed" | "timeout" | "next_point_missing" | "duplicate_loop_detected";

export type FullModalHarvestFailedStage = "no_next_point_calibrated" | "next_click_no_effect" | "modal_id_change_timeout" | "duplicate_loop_detected" | null;

export interface RightRailCalibrationPoint {
  x: number;
  y: number;
  x_ratio: number;
  y_ratio: number;
}

export type RightRailCalibrationVersion = "phase10a" | "phase11g_calibrated_points_with_next" | "phase12a_calibrated_five_point_workflow" | "calibrated_four_point_workflow" | "phase13h_four_point_calibration";

export interface RightRailCalibration {
  version: RightRailCalibrationVersion;
  viewport_width: number;
  viewport_height: number;
  viewport_source?: "content_script";
  points: Record<CalibratedMetricName, RightRailCalibrationPoint> & Partial<Record<"next_video_button", RightRailCalibrationPoint>>;
  created_at: string;
  profile_url_host: string;
}

export interface OcrCropRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CalibratedPointMetricResult {
  metric: CalibratedMetricName;
  source: "calibrated_point_dom" | "calibrated_point_ocr";
  point: {
    x: number;
    y: number;
    x_ratio: number;
    y_ratio: number;
  };
  raw_text: string | null;
  value: number | null;
  candidate_path?: string | null;
  warning_reason?: string | null;
  crop_region?: OcrCropRegion | null;
  ocr_confidence?: number | null;
  crop_debug_data_url?: string | null;
}

export interface ActionRailBlockDiagnostic {
  index: number;
  rect: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
  visible_text: string | null;
  aria_title_class_hints: string | null;
  assigned_metric: "like" | "comment" | "favorite" | "share" | null;
  count_text: string | null;
  count_value: number | null;
}

export interface ActionRailRejectedCandidateDiagnostic {
  visible_text: string | null;
  reason: string;
  rect: {
    x: number;
    y: number;
    width: number;
    height: number;
  };
}

export type ActionRailMissingReason = "no_rail_band" | "no_compact_counts" | "compact_counts_rejected" | "ambiguous_order";

export interface ActionRailRectDiagnostic {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type ActionRailExtractionMode = "accessibility_tree_right_rail" | "screenshot_ocr_right_rail" | "cdp_dom_snapshot_right_rail" | "right_rail_numeric_band" | "right_rail_element_from_point_fallback" | "combined_modal_text_fallback";

export interface ActionRailRailRegionDiagnostic {
  min_x: number;
  max_x: number;
  min_y: number;
  max_y: number;
  source: "viewport_right_band" | "active_video_geometry";
}

export interface CdpDomSnapshotRailLabel {
  text: string;
  value: number;
  rect: ActionRailRectDiagnostic;
  assigned_metric?: "like" | "comment" | "favorite" | "share" | null;
}

export interface CdpDomSnapshotRightRailResult {
  source_used: "cdp_dom_snapshot_right_rail";
  extraction_source: "cdp_dom_snapshot_right_rail";
  confidence: "high";
  viewport_width: number;
  viewport_height: number;
  snapshot_text_count: number;
  compact_labels_found: number;
  right_rail_region: ActionRailRailRegionDiagnostic;
  selected_rail_labels: CdpDomSnapshotRailLabel[];
  rejected_examples: ActionRailRejectedCandidateDiagnostic[];
  warning_reason: string | null;
  status: "PASS" | "WARN" | "FAIL";
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
}

export interface CdpDomSnapshotTextEntry {
  text: string;
  rect: ActionRailRectDiagnostic;
  node_index?: number | null;
  backend_node_id?: number | null;
}

export interface CdpDomSnapshotPayload {
  viewport_width: number;
  viewport_height: number;
  text_entries: CdpDomSnapshotTextEntry[];
}

export interface VisualRightRailLabel {
  text: string;
  value: number;
  rect?: ActionRailRectDiagnostic | null;
  y?: number | null;
  source?: "accessibility_tree" | "screenshot_ocr";
  role?: string | null;
  backend_dom_node_id?: number | null;
}

export interface AccessibilityTreePayload {
  viewport_width: number;
  viewport_height: number;
  nodes: Array<{
    name: string;
    role?: string | null;
    backend_dom_node_id?: number | null;
    ignored?: boolean | null;
    rect?: ActionRailRectDiagnostic | null;
  }>;
}

export interface ScreenshotOcrPayload {
  viewport_width: number;
  viewport_height: number;
  raw_text: string;
  parsed_lines?: string[] | null;
  confidence?: number | null;
  crop_region?: ActionRailRailRegionDiagnostic | null;
}

export interface VisualRightRailDiagnostics {
  source_used: "accessibility_tree_right_rail" | "screenshot_ocr_right_rail" | null;
  accessibility_node_count: number;
  accessibility_compact_labels: VisualRightRailLabel[];
  ocr_used: boolean;
  ocr_raw_text: string | null;
  ocr_parsed_lines: string[];
  ocr_selected_lines: string[];
  crop_region: ActionRailRailRegionDiagnostic | null;
  warning_reason: string | null;
}

export interface VisualRightRailPayload {
  accessibility_tree?: AccessibilityTreePayload | null;
  screenshot_ocr?: ScreenshotOcrPayload | null;
}

export interface ActionRailNumericLabelDiagnostic {
  visible_text: string | null;
  value: number | null;
  rect: ActionRailRectDiagnostic;
  accepted: boolean;
  reason: string | null;
  source: "element" | "element_from_point";
  center_x: number;
  center_y: number;
  nearest_tag?: string | null;
  nearest_class?: string | null;
  nearest_aria_label?: string | null;
  nearest_title?: string | null;
}

export interface ActionRailAssignedMetricDiagnostic {
  metric: "like" | "comment" | "favorite" | "share";
  visible_text: string | null;
  value: number | null;
  rect: ActionRailRectDiagnostic | null;
  source: ActionRailExtractionMode;
}

export interface ActionRailXBandDiagnostic {
  min: number;
  max: number;
  source: "icon_candidates" | "viewport_fallback" | "active_video_geometry" | "compact_count_cluster" | "right_rail_numeric_band";
}

export interface ActionRailCompactCountCandidateDiagnostic {
  visible_text: string | null;
  value: number | null;
  rect: ActionRailRectDiagnostic;
  accepted: boolean;
  reason: string | null;
  source?: "text_node" | "element" | "element_from_point" | null;
  center_x?: number | null;
  center_y?: number | null;
  nearest_tag?: string | null;
  nearest_class?: string | null;
  nearest_aria_label?: string | null;
  nearest_title?: string | null;
}

export interface ActionRailCompactCountClusterDiagnostic {
  id: string;
  center_x: number;
  candidate_count: number;
  y_values: number[];
  score: number;
  accepted: boolean;
  reason: string | null;
  x_band: ActionRailXBandDiagnostic;
  candidates: ActionRailCompactCountCandidateDiagnostic[];
}

export interface RawEvidenceSummary {
  has_network_aweme: boolean;
  has_detail_aweme: boolean;
  has_dom_snapshot: boolean;
  has_dom_detail_metrics?: boolean;
  has_runtime_aweme?: boolean;
  network_keys: string[];
  detail_keys: string[];
  dom_detail_metric_keys?: string[];
  evidence_sources: string[];
  evidence_collection_version:
    | "phase2"
    | "phase5c_detail_hydrate"
    | "phase6h_full_modal_auto_harvest"
    | "phase6j_runtime_state_extraction"
    | "phase7a_cdp_active_tab_harvest"
    | "phase8a_cdp_domsnapshot_right_rail"
    | "phase9a_accessibility_ocr_right_rail"
    | "phase10a_calibrated_point_extractor"
    | "phase10c_smart_capture_harvest"
    | "phase11a_production_stabilized_calibrated_harvest"
    | "phase17a_finalized_only_harvest"
    | "phase12a_calibrated_five_point_workflow"
    | "phase12c_recovered_four_point_harvest"
    | "phase12d_four_point_navigation_loop_fix";
}

export interface NetworkVideoMetadata {
  aweme_id: string;
  title?: string | null;
  desc?: string | null;
  share_url?: string | null;
  thumbnail_url?: string | null;
  cover_url?: string | null;
  origin_cover?: string | null;
  dynamic_cover?: string | null;
  url_list?: string[];
  poster_aspect_ratio?: number | null;
  duration_text?: string | null;
  duration_seconds?: number | null;
  posted_at?: string | null;
  view_count?: number | null;
  like_count?: number | null;
  comment_count?: number | null;
  /** Douyin statistics.collect_count — required for Hybrid finalized payloads. */
  favorite_count?: number | null;
  share_count?: number | null;
  engagement_rate?: number | null;
  view_count_text?: string | null;
  like_count_text?: string | null;
  comment_count_text?: string | null;
  share_count_text?: string | null;
  raw_source?: string | null;
  raw_network_aweme?: RawAwemeEvidence | null;
  raw_detail_aweme?: RawAwemeEvidence | null;
  observed_at?: string | null;
  context?: CaptureContext | null;
  context_mismatch_codes?: ContextMismatchCode[];
}

export interface VideoPayload {
  id?: string | null;
  aweme_id?: string | null;
  video_id?: string | null;
  source_video_url?: string | null;
  share_url?: string | null;
  url?: string | null;
  title?: string | null;
  desc?: string | null;
  thumbnail_url?: string | null;
  poster_url?: string | null;
  cover_url?: string | null;
  cover?: string | null;
  poster?: string | null;
  origin_cover?: string | null;
  dynamic_cover?: string | null;
  animated_cover?: string | null;
  image_url?: string | null;
  url_list?: string[];
  poster_aspect_ratio?: number | null;
  thumbnail_source_types?: string[];
  duration_text?: string | null;
  duration_seconds?: number | null;
  duration_source?: DurationSource | null;
  posted_text?: string | null;
  posted_text_raw?: string | null;
  posted_at?: string | null;
  posted_display?: string | null;
  posted_parse_confidence?: string | null;
  view_count_text?: string | null;
  view_count?: number | null;
  view_count_source?: MetricSource | null;
  like_count_text?: string | null;
  like_count?: number | null;
  like_count_source?: MetricSource | null;
  comment_count_text?: string | null;
  comment_count?: number | null;
  comment_count_source?: MetricSource | null;
  share_count?: number | null;
  share_count_source?: MetricSource | null;
  share_count_text?: string | null;
  engagement_rate?: number | null;
  engagement_rate_source?: EngagementRateSource | null;
  has_speech?: boolean | null;
  text_density?: string | null;
  has_heavy_watermark?: boolean | null;
  processing_complexity?: string | null;
  copyright_risk?: string | null;
  preview_status?: "ready" | "missing";
  source_link_status?: "captured" | "missing";
  media_asset_status?: "not_generated" | "ready" | "failed";
  media_status?: "source_link_captured" | "missing" | "ready";
  thumbnail_source_type?: string | null;
  thumbnail_source?: ThumbnailSource | null;
  thumbnail_missing_reason?: ThumbnailMissingReason | null;
  posted_source?: PostedSource | null;
  network_source?: string | null;
  capture_context?: CaptureContext | null;
  context_mismatch_codes?: ContextMismatchCode[];
  extraction_diagnostics?: Record<string, string | number | boolean | null>;
  raw?: Record<string, string | number | boolean | null | string[]>;
  raw_network_aweme?: RawAwemeEvidence | null;
  raw_detail_aweme?: RawAwemeEvidence | null;
  raw_dom_snapshot?: RawDomSnapshot | null;
  raw_dom_detail_metrics?: RawDomDetailMetrics | null;
  raw_evidence_summary?: RawEvidenceSummary | null;
  statistics: Record<string, number | null>;
}

export interface ProfilePayload {
  id?: string | null;
  sec_uid?: string | null;
  handle?: string | null;
  display_name?: string | null;
}

export interface ExtensionCaptureFailureSummary {
  stage: string;
  item_index?: number | null;
  code: string;
  message: string;
}

export type IncrementalProfileHarvestMode = "new_only" | "new_and_incomplete" | "refresh_all";

export interface IncrementalProfileScanSummary {
  harvest_mode: IncrementalProfileHarvestMode;
  total_found: number;
  new_count: number;
  incomplete_count: number;
  complete_count: number;
  skipped_count: number;
  target_count: number;
  target_aweme_ids: string[];
  new_aweme_ids: string[];
  incomplete_aweme_ids: string[];
  complete_aweme_ids: string[];
  skipped_aweme_ids?: string[];
}

export interface ExtensionCaptureResponse {
  success: boolean;
  diagnostics_id: string;
  capture_id?: string | null;
  detected_page_type: DouyinPageType;
  capture_session_id?: string | null;
  captured_item_count: number;
  normalized_item_count: number;
  duplicate_item_count: number;
  ready_item_count: number;
  skipped_item_count: number;
  failed_item_count: number;
  stage: string;
  error_code?: string | null;
  warning_codes: string[];
  failure_summaries: ExtensionCaptureFailureSummary[];
  visible_captured_count: number;
  submitted_count: number;
  staged_count: number;
  deduped_count: number;
  skipped_count: number;
  failed_count: number;
  warning?: string | null;
  next_suggested_route: string;
  scan_summary?: IncrementalProfileScanSummary;
  total_found?: number;
  new_count?: number;
  incomplete_count?: number;
  complete_count?: number;
  target_aweme_ids?: string[];
  new_aweme_ids?: string[];
  incomplete_aweme_ids?: string[];
  complete_aweme_ids?: string[];
}

export interface ExtensionCapturePayload {
  schema_version: "douyin_extension_capture.v1";
  capture_id: string;
  captured_at: string;
  page: PageSnapshot;
  profile: ProfilePayload | null;
  capture_context: CaptureContext;
  videos: VideoPayload[];
  diagnostics: Record<string, string | number | boolean | null>;
  harvest_mode?: IncrementalProfileHarvestMode;
}

export interface HarvestPlanProfileCardEvidence {
  aweme_id: string;
  source_url?: string | null;
  title?: string | null;
  caption?: string | null;
  desc?: string | null;
  description?: string | null;
  thumbnail_url?: string | null;
  cover_url?: string | null;
  poster_url?: string | null;
  posted_text?: string | null;
  posted_text_raw?: string | null;
  posted_at?: string | null;
  posted_display?: string | null;
  thumbnail_source?: string | null;
  posted_source?: string | null;
  posted_parse_confidence?: string | null;
  posted_parser_pattern_matched?: string | null;
  posted_reference_time?: string | null;
  posted_timezone?: string | null;
  raw_profile_card?: Record<string, unknown> | null;
}

export interface HarvestPlanResponse extends ExtensionCaptureResponse {
  plan_id: string;
  profile_card_evidence_by_aweme_id: Record<string, HarvestPlanProfileCardEvidence>;
  created_visible_item_count: number;
}

export type ModalDataIntegrityStatus = "ok" | "mismatch" | "pending" | "passed" | "failed";

export interface FullModalHarvestItemPayload {
  aweme_id: string;
  target_aweme_id?: string | null;
  source_video_external_id?: string | null;
  metadata_status?: string | null;
  review_status?: string | null;
  source_url?: string | null;
  page_url?: string | null;
  modal_id?: string | null;
  raw_dom_detail_metrics: RawDomDetailMetrics;
  raw_detail_aweme?: RawAwemeEvidence | null;
  raw_evidence_summary: RawEvidenceSummary;
  profile_card_evidence?: HarvestPlanProfileCardEvidence | null;
  modal_aweme_id_before_extract?: string | null;
  modal_aweme_id_after_extract?: string | null;
  extracted_aweme_id?: string | null;
  data_integrity_status?: ModalDataIntegrityStatus;
  data_integrity_reason?: string | null;
  metric_signature?: string | null;
  duplicate_signature_warning?: string | null;
  view_count?: number | null;
  real_view_count_available?: boolean | null;
  real_view_count_data_quality?: string | null;
  estimated_views?: number | null;
  estimated_views_formula?: "tiered_like_multiplier_v1" | string | null;
  estimated_views_used?: boolean | null;
  real_view_count_overwritten?: boolean | null;
}

export type ExtensionBackendErrorCode =
  | "backend_unreachable"
  | "cors_or_permission_blocked"
  | "request_timeout"
  | "capture_session_not_found"
  | "capture_session_profile_mismatch"
  | "http_422_schema_error"
  | "http_500_server_error"
  | "http_4xx_client_error"
  | "auth_required"
  | "network_failed";

export type FullModalHarvestPendingFlushStatus = "pending" | "flushing" | "flushed" | "failed_retryable" | "failed_terminal";

export interface FullModalHarvestPendingFlushItem {
  id: string;
  capture_session_id: string | null;
  aweme_id: string;
  payload_item: FullModalHarvestItemPayload;
  created_at: string;
  attempts: number;
  last_error: string | null;
  last_error_code?: ExtensionBackendErrorCode | null;
  status: FullModalHarvestPendingFlushStatus;
}

export type FullModalHarvestStatus = "idle" | "running" | "paused" | "completed" | "completed_with_warnings" | "failed";

export type FullModalHarvestPhase =
  | "starting"
  | "capturing_profile"
  | "harvesting"
  | "loading_next_video"
  | "waiting_modal_change"
  | "extracting_metrics"
  | "queued_item"
  | "flushing"
  | "paused"
  | "stopped"
  | "completed"
  | "completed_with_warnings"
  | "failed";

export type FullModalHarvestCurrentState = "starting" | "harvesting" | "paused" | "stopped" | "completed" | "completed_with_warnings" | "failed";

export type FullModalHarvestTargetStatusValue = "pending" | "extracting" | "extracted" | "updated" | "failed" | "skipped";

export type FullModalHarvestItemStage = "idle" | "extracting" | "extracted" | "committing" | "queued" | "flushing" | "navigating";

export interface FullModalHarvestTargetStatus {
  aweme_id: string;
  index: number;
  status: FullModalHarvestTargetStatusValue;
  reason?: string | null;
  attempts: number;
  updated_at: string;
}

export type FullModalHarvestMode = "full_harvest" | "retry_failed";

export type FullModalHarvestFlushStatus = "success" | "failed" | "none" | "retrying" | "queued";

export interface FullModalHarvestProgress {
  running: boolean;
  harvest_status?: FullModalHarvestStatus;
  harvest_loop_heartbeat_at?: string | null;
  current_state?: FullModalHarvestCurrentState;
  phase?: FullModalHarvestPhase;
  target_count: number;
  current_index?: number;
  current_aweme_id: string | null;
  current_video_url?: string | null;
  current_caption_snippet?: string | null;
  harvested_count: number;
  processed_count?: number;
  updated_count: number;
  skipped_count?: number;
  remaining_count?: number;
  pending_count?: number;
  duplicate_count: number;
  consecutive_duplicate_count?: number;
  failed_count: number;
  flushed_count: number;
  flush_attempt_count?: number;
  elapsed_seconds?: number;
  average_seconds_per_item?: number | null;
  eta_seconds?: number | null;
  last_error: string | null;
  stopped_reason: string | null;
  failed_at_index?: number | null;
  failed_aweme_id?: string | null;
  can_resume?: boolean;
  detector_diagnostics?: FullModalHarvestDetectorDiagnostics | null;
  flush_url?: string | null;
  flush_status_code?: number | null;
  flush_error_code?: ExtensionBackendErrorCode | null;
  flush_error_message?: string | null;
  flush_retryable?: boolean | null;
  flush_next_action?: string | null;
  pending_count_before_flush?: number | null;
  pending_count_after_flush?: number | null;
  last_flush_status?: FullModalHarvestFlushStatus;
  next_flush_in_items?: number | null;
  backend_response_summary?: Record<string, string | number | boolean | null> | null;
  last_harvested_item?: FullModalHarvestLastItemSummary | null;
  last_extracted_metrics?: FullModalHarvestProbeResult | null;
  item_stage?: FullModalHarvestItemStage;
  phase_elapsed_ms?: number | null;
  extracted_not_committed_ms?: number | null;
  last_commit_result?: "success" | "retryable_failed" | "failed" | null;
  repair_extracted_not_committed_count?: number;
  integrity_mismatch_count?: number;
  last_integrity_error?: string | null;
  last_integrity_expected_aweme_id?: string | null;
  last_integrity_observed_aweme_id?: string | null;
  last_integrity_checked_at?: string | null;
  recent_items?: FullModalHarvestLastItemSummary[] | null;
  runtime_transition_log?: HarvestRuntimeV2TransitionLogEntry[] | null;
  source_used?: string | null;
  cdp_attached?: boolean;
  cdp_response_count?: number;
  cdp_exact_match_count?: number;
  calibration_status?: "calibrated" | "missing";
  calibrated_viewport?: { width: number; height: number } | null;
  current_viewport?: { width: number; height: number } | null;
  next_point_status?: FullModalHarvestNextPointStatus;
  previous_aweme_id?: string | null;
  navigation_retries?: number;
  last_navigation_result?: FullModalHarvestNavigationResult | null;
  failed_stage?: FullModalHarvestFailedStage;
  mode?: FullModalHarvestMode;
  target_status_map?: Record<string, FullModalHarvestTargetStatus>;
  failed_targets?: FullModalHarvestTargetStatus[];
  retry_failed_current?: number;
  retry_failed_total?: number;
}

export interface FullModalHarvestDetectorDiagnostics {
  current_url: string;
  location_search: string;
  modal_id_from_url: string | null;
  path_video_id: string | null;
  video_element_count: number;
  active_video_duration: number | null;
  detector_error: string | null;
}

export interface FullModalHarvestLastItemSummary {
  index?: number | null;
  aweme_id: string;
  duration_seconds: number | null;
  duration_text?: string | null;
  like_count: number | null;
  like_count_source?: string | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  view_count?: number | null;
  source_used?: string | null;
  missing_fields?: string[] | null;
  posted_text?: string | null;
  extraction_warning: string | null;
  status?: string | null;
  reason?: string | null;
  target_aweme_id?: string | null;
  extracted_aweme_id?: string | null;
  data_integrity_status?: ModalDataIntegrityStatus;
  data_integrity_reason?: string | null;
  metric_signature?: string | null;
  duplicate_signature_warning?: string | null;
}

export interface FullModalHarvestProbeResult {
  aweme_id: string | null;
  calibration_status?: "calibrated" | "missing";
  calibrated_viewport?: { width: number; height: number } | null;
  current_viewport?: { width: number; height: number } | null;
  source_priority_used?: ModalMetadataSourcePriority;
  source_used?: string | null;
  exact_aweme_runtime_found?: boolean;
  exact_aweme_found?: boolean;
  exact_aweme_source?: ExactAwemeRuntimeSource;
  raw_aweme_keys?: string[] | null;
  fallback_used?: ModalMetadataSourcePriority | null;
  rejected_reason?: string | null;
  cdp_attached?: boolean;
  cdp_response_count?: number;
  cdp_json_response_count?: number;
  cdp_candidate_aweme_count?: number;
  cdp_exact_match_count?: number;
  runtime_exact_match_count?: number;
  last_matching_aweme_id?: string | null;
  last_matching_response_url?: string | null;
  cdp_last_error?: string | null;
  current_modal_id_before?: string | null;
  current_modal_id_after?: string | null;
  extracted_aweme_id?: string | null;
  duration_seconds: number | null;
  duration_text: string | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  view_count?: number | null;
  posted_text: string | null;
  posted_at?: string | null;
  point_results?: Record<string, CalibratedPointMetricResult> | null;
  confidence_by_field?: Record<string, string> | null;
  rejected_metric_reasons?: Record<string, string> | null;
  action_blocks_found: number;
  modal_action_blocks_found?: number | null;
  action_block_diagnostics?: ActionRailBlockDiagnostic[] | null;
  accepted_action_blocks?: ActionRailBlockDiagnostic[] | null;
  rejected_candidates_count?: number | null;
  rejected_candidate_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  rail_x_band?: ActionRailXBandDiagnostic | null;
  computed_rail_x_band?: ActionRailXBandDiagnostic | null;
  viewport_width?: number | null;
  viewport_height?: number | null;
  active_video_rect?: ActionRailRectDiagnostic | null;
  modal_candidate_rect?: ActionRailRectDiagnostic | null;
  rail_region?: ActionRailRailRegionDiagnostic | null;
  numeric_labels_found?: ActionRailNumericLabelDiagnostic[] | null;
  selected_rail_labels?: string[] | null;
  selected_rail_labels_with_rect?: ActionRailNumericLabelDiagnostic[] | null;
  assigned_metrics?: ActionRailAssignedMetricDiagnostic[] | null;
  rejected_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  extraction_mode?: ActionRailExtractionMode | null;
  snapshot_text_count?: number | null;
  compact_labels_found?: number | null;
  right_rail_region?: ActionRailRailRegionDiagnostic | null;
  selected_snapshot_rail_labels?: CdpDomSnapshotRailLabel[] | null;
  accessibility_node_count?: number | null;
  accessibility_compact_labels?: VisualRightRailLabel[] | null;
  ocr_used?: boolean | null;
  ocr_raw_text?: string | null;
  ocr_selected_lines?: string[] | null;
  visual_extractor_diagnostics?: VisualRightRailDiagnostics | null;
  combined_text_segment?: string | null;
  combined_count_tokens?: string[] | null;
  icon_candidates?: ActionRailIconCandidateDiagnostic[] | null;
  selected_action_icons?: ActionRailIconCandidateDiagnostic[] | null;
  icon_anchored_metrics?: ActionRailIconAnchoredMetricDiagnostic[] | null;
  rejected_number_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  rejected_icon_examples?: ActionRailRejectedCandidateDiagnostic[] | null;
  compact_count_candidates?: ActionRailCompactCountCandidateDiagnostic[] | null;
  compact_text_node_candidates_count?: number | null;
  compact_count_clusters?: ActionRailCompactCountClusterDiagnostic[] | null;
  selected_compact_count_cluster?: ActionRailCompactCountClusterDiagnostic | null;
  selected_cluster_texts?: string[] | null;
  selected_cluster_rects?: ActionRailRectDiagnostic[] | null;
  action_blocks_missing_reason?: ActionRailMissingReason | null;
  extraction_warning?: string | null;
  warning_reason?: string | null;
  probe_status?: "PASS" | "WARN" | "FAIL";
  ready_for_full_harvest: boolean;
  blocking_reason?: string | null;
}

export interface FullModalHarvestFailedItem {
  aweme_id: string;
  reason: string;
}

export interface StoredFullModalHarvestState {
  harvest_id: string;
  harvest_status?: FullModalHarvestStatus;
  harvest_loop_heartbeat_at?: string | null;
  session_id?: string | null;
  target_count: number;
  started_at: string;
  updated_at: string;
  current_aweme_id: string | null;
  current_video_url?: string | null;
  phase?: FullModalHarvestPhase;
  current_state?: FullModalHarvestCurrentState;
  harvested_aweme_ids: string[];
  pending_items: FullModalHarvestItemPayload[];
  pending_flush_queue?: FullModalHarvestPendingFlushItem[];
  flushed_aweme_ids: string[];
  failed_items: FullModalHarvestFailedItem[];
  target_status_map?: Record<string, FullModalHarvestTargetStatus>;
  mode?: FullModalHarvestMode;
  consecutive_failures?: number;
  duplicate_count: number;
  consecutive_duplicate_count?: number;
  updated_count: number;
  stopped_reason: string | null;
  last_error: string | null;
  failed_at_index?: number | null;
  failed_aweme_id?: string | null;
  last_flush_status?: FullModalHarvestFlushStatus;
  detector_diagnostics?: FullModalHarvestDetectorDiagnostics | null;
  flush_url?: string | null;
  flush_status_code?: number | null;
  flush_error_code?: ExtensionBackendErrorCode | null;
  flush_error_message?: string | null;
  flush_retryable?: boolean | null;
  flush_next_action?: string | null;
  pending_count_before_flush?: number | null;
  pending_count_after_flush?: number | null;
  backend_response_summary?: Record<string, string | number | boolean | null> | null;
  last_harvested_item?: FullModalHarvestLastItemSummary | null;
  last_extracted_metrics?: FullModalHarvestProbeResult | null;
  item_stage?: FullModalHarvestItemStage;
  phase_elapsed_ms?: number | null;
  extracted_not_committed_ms?: number | null;
  last_commit_result?: "success" | "retryable_failed" | "failed" | null;
  repair_extracted_not_committed_count?: number;
  integrity_mismatch_count?: number;
  last_integrity_error?: string | null;
  last_integrity_expected_aweme_id?: string | null;
  last_integrity_observed_aweme_id?: string | null;
  last_integrity_checked_at?: string | null;
  recent_items?: FullModalHarvestLastItemSummary[] | null;
  calibration?: RightRailCalibration | null;
  target_aweme_ids?: string[];
  next_point_status?: FullModalHarvestNextPointStatus;
  previous_aweme_id?: string | null;
  navigation_retries?: number;
  last_navigation_result?: FullModalHarvestNavigationResult | null;
  failed_stage?: FullModalHarvestFailedStage;
  config: FullModalHarvestControlOptions;
}

export interface FullModalHarvestControlOptions {
  target_count?: number;
  delay_between_items_ms?: number;
  per_item_timeout_ms?: number;
  flush_every_n_items?: number;
  stop_on_captcha?: boolean;
  stop_on_no_next?: boolean;
  allow_probe_warnings?: boolean;
  capture_session_id?: string | null;
  capture_id?: string | null;
  target_aweme_ids?: string[];
  retry_failed_only?: boolean;
  profile_card_evidence_by_aweme_id?: Record<string, HarvestPlanProfileCardEvidence>;
}

export type SmartCaptureHarvestWorkflowState =
  | "idle"
  | "backend_unavailable"
  | "unsupported_tab"
  | "content_script_unavailable"
  | "detector_unavailable"
  | "profile_capture_required"
  | "capture_session_required"
  | "capturing_profile"
  | "resolving_profile_queue"
  | "capture_ready"
  | "calibration_required"
  | "modal_required"
  | "probe_required"
  | "probe_ready"
  | "harvest_ready"
  | "harvesting"
  | "loading_next_video"
  | "waiting_modal_change"
  | "flushing"
  | "paused"
  | "completed"
  | "completed_with_warnings"
  | "completed_noop"
  | "failed";

export interface SmartCaptureHarvestState {
  current_state: SmartCaptureHarvestWorkflowState;
  next_required_action: string | null;
  latest_capture_session_id: string | null;
  latest_capture_id: string | null;
  captured_item_count: number;
  captured_at: string | null;
  profile_url: string | null;
  last_probe_status: "PASS" | "WARN" | "FAIL" | "none";
  calibration_status: "calibrated" | "partial" | "missing";
  target_count: number;
  target_aweme_ids: string[];
  target_status_map?: Record<string, FullModalHarvestTargetStatus>;
  harvest_mode?: IncrementalProfileHarvestMode | undefined;
  scan_summary?: IncrementalProfileScanSummary | undefined;
  mode?: FullModalHarvestMode;
  current_index: number;
  current_aweme_id: string | null;
  harvested_count: number;
  flushed_count: number;
  updated_count: number;
  failed_count: number;
  profile_card_evidence_by_aweme_id?: Record<string, HarvestPlanProfileCardEvidence>;
  skipped_count?: number;
  remaining_count?: number;
  eta_seconds: number | null;
  last_error: string | null;
  updated_at: string;
}

export type HarvestRuntimeV2Status = "idle" | "running" | "paused" | "completed" | "completed_with_warnings" | "failed";
export type HarvestRuntimeV2Phase =
  | "idle"
  | "resolving_plan"
  | "opening_target"
  | "waiting_modal"
  | "settling_modal"
  | "extracting"
  | "validating"
  | "flushing"
  | "marking_updated"
  | "advancing"
  | "completed"
  | "failed"
  | "paused";
export type HarvestRuntimeV2PauseReason =
  | null
  | "operator_stop"
  | "backend_flush_failed"
  | "content_script_unavailable"
  | "calibration_invalid"
  | "captcha_required"
  | "consecutive_failures"
  | "harvest_loop_inactive";

export interface HarvestRuntimeV2TargetStatus {
  index: number;
  status: "pending" | "processing" | "updated" | "failed" | "skipped";
  attempts: number;
  last_error: string | null;
}

export interface HarvestRuntimeV2TransitionLogEntry {
  timestamp: string;
  from_status: HarvestRuntimeV2Status;
  to_status: HarvestRuntimeV2Status;
  from_phase: HarvestRuntimeV2Phase;
  to_phase: HarvestRuntimeV2Phase;
  reason: string | null;
  caller: string;
  stack_or_location: string | null;
  target_index: number;
  aweme_id: string | null;
}

export interface HarvestRuntimeV2State {
  schema_version: "phase17c_safe_runner";
  run_id: string | null;
  status: HarvestRuntimeV2Status;
  phase: HarvestRuntimeV2Phase;
  pause_reason: HarvestRuntimeV2PauseReason;
  target_aweme_ids: string[];
  target_status: Record<string, HarvestRuntimeV2TargetStatus>;
  current_target_index: number;
  current_aweme_id: string | null;
  previous_aweme_id: string | null;
  counts: {
    target: number;
    updated: number;
    failed: number;
    skipped: number;
    pending_flush: number;
    flushed: number;
    flush_attempt_count?: number;
    duplicates: number;
  };
  last_metrics: FullModalHarvestProbeResult | null;
  recent_items: FullModalHarvestLastItemSummary[];
  profile_card_evidence_by_aweme_id: Record<string, HarvestPlanProfileCardEvidence>;
  state_transition_log?: HarvestRuntimeV2TransitionLogEntry[];
  started_at: string | null;
  updated_at: string | null;
  heartbeat_at: string | null;
  last_error: string | null;
}

export type SafeHarvestRunStatus = "idle" | "running" | "paused" | "completed" | "completed_with_warnings" | "failed";

export type SafeHarvestRunPhase = HarvestRuntimeV2Phase;

export type SafeHarvestRunStopReason = HarvestRuntimeV2PauseReason;

export interface SafeHarvestRunTargetStatus {
  index: number;
  status: "pending" | "processing" | "updated" | "failed" | "skipped";
  attempts: number;
  last_error: string | null;
  last_integrity_status?: "ok" | "mismatch" | null;
  last_expected_aweme_id?: string | null;
  last_observed_aweme_id?: string | null;
}

export interface SafeHarvestRunTransitionLogEntry {
  timestamp: string;
  from_status: SafeHarvestRunStatus;
  to_status: SafeHarvestRunStatus;
  from_phase: SafeHarvestRunPhase;
  to_phase: SafeHarvestRunPhase;
  reason: string | null;
  caller: string;
  stack_or_location: string | null;
  target_index: number;
  aweme_id: string | null;
}

export interface SafeHarvestRunState {
  schema_version: "phase17c_safe_runner";
  run_id: string | null;
  status: SafeHarvestRunStatus;
  phase: SafeHarvestRunPhase;
  stop_reason: SafeHarvestRunStopReason;
  profile_url: string | null;
  capture_session_id: string | null;
  capture_id: string | null;
  target_aweme_ids: string[];
  target_status: Record<string, SafeHarvestRunTargetStatus>;
  current_target_index: number;
  current_aweme_id: string | null;
  previous_aweme_id: string | null;
  counts: {
    target: number;
    updated: number;
    failed: number;
    skipped: number;
    pending_flush: number;
    flushed: number;
    duplicates: number;
    integrity_mismatch: number;
  };
  last_metrics: FullModalHarvestProbeResult | null;
  recent_items: FullModalHarvestLastItemSummary[];
  state_transition_log?: SafeHarvestRunTransitionLogEntry[];
  started_at: string | null;
  updated_at: string | null;
  heartbeat_at: string | null;
  last_error: string | null;
}

export type DouyinExtensionCaptureSessionSource = "whole_profile_harvest" | "whole_profile_staged_harvest_v2";

export interface DouyinExtensionCaptureSessionRequest {
  schema_version: "douyin_extension_capture_session.v1";
  source: DouyinExtensionCaptureSessionSource;
  profile_url: string;
  normalized_profile_url?: string;
  profile_sec_uid_or_path?: string | null;
  profile_display_name?: string | null;
  profile_avatar_url?: string | null;
  display_title?: string;
  source_modal_aweme_id?: string | null;
  verified_target_count: number;
  queued_count?: number;
  run_id: string;
  mode: DouyinExtensionCaptureSessionSource;
}

export interface DouyinExtensionCaptureSessionResponse {
  ok?: boolean;
  session_id: string;
  created: boolean;
  profile_url: string;
  source: string;
  run_id?: string;
}

export interface FullModalHarvestRequestPayload {
  schema_version: "douyin_full_modal_harvest.v1";
  capture_session_id?: string | null;
  capture_session_source?: string | null;
  run_id?: string | null;
  profile_url?: string | null;
  target_aweme_id?: string | null;
  source_video_external_id?: string | null;
  started_at: string;
  page: PageSnapshot;
  capture_context: CaptureContext;
  items: FullModalHarvestItemPayload[];
  progress: FullModalHarvestProgress;
  diagnostics?: Record<string, string | number | boolean | null>;
  commit_policy?: "legacy_update_existing" | "finalized_only";
}

export interface FullModalHarvestResponse {
  success: boolean;
  ok?: boolean;
  capture_session_id?: string | null;
  capture_inbox_item_id?: string | null;
  source_video_external_id?: string | null;
  metadata_status?: string | null;
  item_created_or_updated?: boolean;
  target_count: number;
  harvested_count: number;
  matched_count: number;
  updated_count: number;
  unchanged_count?: number;
  failed_count?: number;
  duration_updated_count: number;
  like_updated_count: number;
  comment_updated_count: number;
  favorite_updated_count: number;
  share_updated_count: number;
  unmatched_count: number;
  flushed_aweme_ids?: string[];
  failure_summaries?: FullModalHarvestFailedItem[];
  stopped_reason: string | null;
  accepted_count?: number;
  rejected_count?: number;
  estimated_views_received_count?: number;
  estimated_views_persisted_count?: number;
  accepted_not_persisted_count?: number;
  view_count_null_received_count?: number;
  real_view_count_data_quality_received_count?: number;
  estimated_views_accepted_but_not_persisted?: "yes" | "no" | string;
}

export interface NetworkCacheMessage {
  type: "REUP_DOUYIN_NETWORK_CACHE_UPDATE";
  items: NetworkVideoMetadata[];
}

export interface PassiveNetworkProbeTarget22C12A {
  aweme_id: string;
  source_url: string;
  request_url?: string | null;
  desc: string | null;
  cover_url: string | null;
  duration: number | null;
  create_time: number | null;
  like_count: number | null;
  comment_count: number | null;
  /** Douyin statistics.collect_count — required for Hybrid finalized payloads. */
  favorite_count: number | null;
  share_count: number | null;
  author_uid?: string | null;
  author_sec_uid?: string | null;
  author_unique_id?: string | null;
}

export type PassiveNetworkProbeEndpointKind22C12A = "profile_post" | "favorite" | "other_aweme_list";

export interface PassiveNetworkProbeStoredTarget22C12A extends PassiveNetworkProbeTarget22C12A {
  profile_url: string;
  endpoint_path: string;
  endpoint_kind: PassiveNetworkProbeEndpointKind22C12A;
  captured_at: string;
  trace_version: "22C-12A-R3";
}

export interface PassiveNetworkProbeCursorFields22C12BR2 {
  cursor: string | number | null;
  max_cursor: string | number | null;
  min_cursor: string | number | null;
  next_cursor: string | number | null;
  has_more: boolean | null;
  hasMore: boolean | null;
  offset: string | number | null;
  page: string | number | null;
  next: string | number | null;
}

export interface PassiveNetworkProbeBatchMessage22C12A {
  type: "REUP_DOUYIN_NETWORK_AWEME_BATCH_22C12A_R3";
  traceVersion: "22C-12A-R3";
  urlPath: string;
  requestUrl?: string | null;
  method: string;
  status: number | null;
  detectedShape: string;
  hasMore: boolean | null;
  cursor: string | number | null;
  cursorFields?: PassiveNetworkProbeCursorFields22C12BR2;
  awemeCount: number;
  targets: PassiveNetworkProbeTarget22C12A[];
}

export type ExtensionSetupStatus =
  | "not_installed_or_not_connected"
  | "installed_not_connected"
  | "connected"
  | "version_mismatch"
  | "backend_unreachable_from_extension"
  | "stale_connection";

export type ExtensionBrowserFamily = "chrome" | "edge" | "chromium" | "unknown";

export interface ExtensionHandshakeRequest {
  install_id: string;
  extension_id?: string | null;
  extension_version: string;
  browser_family: ExtensionBrowserFamily;
  api_base_url?: string | null;
  client_time: string;
}

export interface ExtensionStatusResponse {
  status: ExtensionSetupStatus;
  connected: boolean;
  install_id?: string | null;
  extension_id?: string | null;
  extension_version?: string | null;
  browser_family?: ExtensionBrowserFamily | null;
  api_base_url?: string | null;
  last_seen_at?: string | null;
  stale_after_seconds: number;
  backend_checked_at: string;
  backend_expected_extension_version: string;
  backend_supported_extension_versions: string[];
  version_status: "compatible" | "version_mismatch" | "unknown";
  compatible: boolean;
  recommended_next_action: string;
  recommended_next_action_label: string;
  operator_message: string;
  download_available: boolean;
  download_url: string;
  manual_install_required: boolean;
  chrome_extensions_url: string;
  edge_extensions_url: string;
}

export interface DouyinPageViewport {
  width: number;
  height: number;
  visual_width: number | null;
  visual_height: number | null;
  device_pixel_ratio: number;
  url: string;
  modal_id: string | null;
  source: "content_script";
}

export type DouyinPageContextType = "profile" | "modal" | "video" | "unknown";

export interface DouyinPageContext {
  success: true;
  url: string;
  current_url?: string;
  host: string;
  page_type: DouyinPageContextType;
  detector_status?: "ready" | "failed";
  is_profile_page: boolean;
  has_modal: boolean;
  modal_id: string | null;
  profile_url?: string | null;
  user_profile_path: string | null;
  viewport: DouyinPageViewport;
}

export interface DouyinContentScriptPong {
  success: true;
  type: "REUP_DOUYIN_PONG";
  ready: true;
  url: string;
  version: string;
  page_context: DouyinPageContext;
  viewport: DouyinPageViewport;
}

export interface DouyinProfileVideoEvidenceProbe {
  current_url: string | null;
  page_type: "profile" | "modal" | "video" | "unknown";
  modal_id_present: boolean;
  document_ready_state: string | null;
  profile_grid_candidate_count: number;
  video_aweme_candidate_count: number;
  visible_link_count: number;
  grid_container_count: number;
  profile_section_count: number;
  profile_tab_count: number;
  profile_title_present: boolean;
  app_root_present: boolean;
  body_text_sample: string;
  diagnostics: Record<string, unknown>;
}

export interface ExtensionMessage {
  type:
    | "GET_DOUYIN_PAGE_VIEWPORT"
    | "DOUYIN_SCANNER_PING"
        | "DOUYIN_NETWORK_PROBE_STATUS_22C12A_R3"
    | "DOUYIN_MANUAL_PAGINATION_TRUTH_TEST_22C13A"
    | "DOUYIN_PROFILE_DOM_PROBE"
    | "REUP_DOUYIN_PING"
    | "REUP_DOUYIN_DETECT_PAGE_CONTEXT"
    | "REUP_DOUYIN_DETECT"
    | "REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE_PING"
    | "REUP_DOUYIN_MODAL_TEST_SCAN_PROFILE"
    | "REUP_DOUYIN_CAPTURE"
    | "REUP_DOUYIN_START_RIGHT_RAIL_CALIBRATION"
    | "REUP_DOUYIN_STOP_RIGHT_RAIL_CALIBRATION"
    | "REUP_DOUYIN_CLEAR_RIGHT_RAIL_CALIBRATION"
    | "REUP_DOUYIN_SHOW_RIGHT_RAIL_CALIBRATION"
    | "REUP_DOUYIN_START_FULL_MODAL_HARVEST"
    | "REUP_DOUYIN_RESUME_FULL_MODAL_HARVEST"
    | "REUP_DOUYIN_RETRY_FAILED_FULL_MODAL_HARVEST"
    | "REUP_DOUYIN_STOP_FULL_MODAL_HARVEST"
    | "REUP_DOUYIN_FLUSH_FULL_MODAL_HARVEST"
    | "REUP_DOUYIN_GET_FULL_MODAL_HARVEST_PROGRESS"
    | "REUP_DOUYIN_RESET_FULL_MODAL_HARVEST_STATE"
    | "REUP_DOUYIN_START_HARVEST_V2"
    | "REUP_DOUYIN_RESUME_HARVEST_V2"
    | "REUP_DOUYIN_STOP_HARVEST_V2"
    | "REUP_DOUYIN_GET_HARVEST_RUNTIME_V2"
    | "REUP_DOUYIN_RESET_HARVEST_RUNTIME_V2"
    | "REUP_DOUYIN_START_SAFE_HARVEST_RUN"
    | "REUP_DOUYIN_RESUME_SAFE_HARVEST_RUN"
    | "REUP_DOUYIN_STOP_SAFE_HARVEST_RUN"
    | "REUP_DOUYIN_GET_SAFE_HARVEST_RUN"
    | "REUP_DOUYIN_RESET_SAFE_HARVEST_RUN"
    | "REUP_DOUYIN_PROBE_CURRENT_MODAL"
    | "REUP_DOUYIN_PROBE_PROFILE_VIDEO_EVIDENCE"
    | "REUP_DOUYIN_CLOSE_MODAL_IF_PRESENT"
    | "REUP_DOUYIN_POST_BACKEND"
    | "REUP_DOUYIN_SYNC_AUTH_SESSION_22C13A"
    | "REUP_DOUYIN_CDP_START"
    | "REUP_DOUYIN_CDP_STOP"
    | "REUP_DOUYIN_CDP_STATUS"
    | "REUP_DOUYIN_CDP_REFRESH_MODAL"
    | "REUP_DOUYIN_CDP_GET_AWEME"
    | "REUP_DOUYIN_CDP_RUNTIME_SCAN"
    | "REUP_DOUYIN_CDP_DOM_SNAPSHOT"
    | "REUP_DOUYIN_VISUAL_RIGHT_RAIL"
    | "REUP_DOUYIN_CAPTURE_VISIBLE_TAB"
    | "DOUYIN_RUNTIME_AUTHORITY_SNAPSHOT_22C11B"
    | "DOUYIN_SCANNER_START_SCAN_PROFILE"
    | "DOUYIN_SCANNER_START_SCAN_PROFILE_22C11B"
    | "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B_PING"
    | "DOUYIN_SCAN_PROFILE_MINIMAL_22C11B"
    | "DOUYIN_SCAN_PROFILE_POST_PAGE_22C14B"
    | "DOUYIN_HYBRID_TAIL_GAP_DOM_SCROLL_PROBE"
    | "DOUYIN_PROFILE_DOM_PROBE_22C11B"
    | "DOUYIN_HYBRID_NETWORK_CACHE_RUNNER"
    | "DOUYIN_HYBRID_UNATTENDED_COLLECT_ALL"
    | "DOUYIN_SCANNER_SKIP_HYBRID_INCOMPLETE"
    | "DOUYIN_SCANNER_CLOSE_UNREACHABLE_TAIL_GAP";
  tab_id?: number | null;
  options?: FullModalHarvestControlOptions | null;
  request?: ExtensionBackendPostRequest | null;
  base_url?: string | null;
  aweme_id?: string | null;
  run_id?: string | null;
  expected_profile_url?: string | null;
  expectedProfileVideoCount?: number | null;
  expected_profile_video_count?: number | null;
  profileUrl?: string | null;
  mode?: "verify_only" | "dry_run_first_n" | null;
  coverage_mode?: "refresh_all" | null;
  traceVersion?: string | null;
  scan_run_id?: string | null;
  scanRunId?: string | null;
  scan_job_id?: string | null;
  cursor?: string | number | null;
  page_index?: number | null;
  max_rounds?: number | null;
  max_duration_ms?: number | null;
  requestedAt?: string | null;
  tabContext?: { tabId?: number | null; url?: string | null; title?: string | null; windowId?: number | null } | null;
}

export interface ExtensionMessageResponse {
  ok: boolean;
  success?: boolean;
  code?: string;
  page?: PageSnapshot;
  payload?: ExtensionCapturePayload;
  calibration?: RightRailCalibration | null;
  calibration_mode_active_before_stop?: boolean;
  calibration_mode_stopped?: boolean;
  harvest_payload?: FullModalHarvestRequestPayload;
  harvest_progress?: FullModalHarvestProgress;
  harvest_runtime_v2?: HarvestRuntimeV2State;
  harvest_response?: FullModalHarvestResponse;
  harvest_probe?: FullModalHarvestProbeResult;
  backend_post?: ExtensionBackendPostResponse;
  screenshot_data_url?: string | null;
  cdp_status?: CdpAwemeStatus;
  cdp_aweme?: CdpAwemeEvidence | null;
  cdp_dom_snapshot?: CdpDomSnapshotPayload | null;
  visual_right_rail?: VisualRightRailPayload | null;
  type?: "REUP_DOUYIN_PONG";
  viewport?: DouyinPageViewport;
  page_context?: DouyinPageContext;
  pong?: DouyinContentScriptPong;
  ready?: boolean;
  url?: string;
  version?: string;
  contentScriptVersion?: string;
  content_script_version?: string;
  handlers?: string[];
  content_script_supported_handlers?: string[];
  messageTypeHandled?: string;
  detector_status?: "ready" | "failed";
  current_url?: string;
  handler_registered?: boolean;
  handler?: string;
  scanner_available?: boolean;
  scanner_function?: string;
  cards?: unknown[];
  total_cards_found?: number;
  schema_version?: string;
  verified_targets?: string[];
  verified_target_details?: unknown[];
  scan_rounds?: number;
  stop_reason?: string | null;
  total_candidates?: number;
  rejected_count?: number;
  rejected_reasons?: string[] | Record<string, number>;
  error_safe?: string;
  failed_stage?: string;
  traceVersion?: string;
  diagnostics?: Record<string, unknown>;
  runtime_authority_snapshot?: Record<string, unknown>;
  network_probe_summary?: Record<string, unknown>;
  profile_dom_probe?: Record<string, unknown>;
  tail_reconcile_candidate_ids?: string[];
  profile_video_evidence?: DouyinProfileVideoEvidenceProbe;
  attempted?: boolean;
  modal_still_visible?: boolean;
  reason?: string | null;
  scanner_started?: boolean;
  accepted?: boolean;
  scanner_runtime_owner?: "background" | "popup";
  scan_run_id?: string | null;
  scanner_invocation_mode?: "direct_same_context" | "content_script_message" | "reconnected_message";
  error?: string;
}

export interface ExtensionBackendPostRequest {
  base_url: string;
  path: string;
  method?: "GET" | "POST";
  payload?: unknown;
  keepalive?: boolean;
  headers?: Record<string, string>;
}

export interface ExtensionBackendPostResponse {
  ok: boolean;
  url: string;
  status_code: number | null;
  body?: Record<string, unknown> | null;
  error_code?: ExtensionBackendErrorCode | null;
  error_message?: string | null;
  retryable?: boolean | null;
}


