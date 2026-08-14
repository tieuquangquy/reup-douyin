export type CaptureSessionStatus =
  | "RECEIVED"
  | "ENRICHING"
  | "READY_FOR_REVIEW"
  | "PARTIALLY_PROMOTED"
  | "PROMOTED"
  | "FAILED";

export type CapturedItemStatus =
  | "RAW"
  | "ENRICHED"
  | "READY"
  | "NEEDS_ENRICHMENT"
  | "PREVIEW_MISSING"
  | "DUPLICATE"
  | "EXCLUDED"
  | "PROMOTED"
  | "FAILED";

export type StudioItemStatusFilter = "all" | "ready" | "needs_action" | "failed" | "duplicate" | "promoted";

export type CaptureInboxAction =
  | "retry_enrich"
  | "retry_preview"
  | "promote_now"
  | "exclude"
  | "delete_items"
  | "open_source"
  | "view_raw_details"
  | "re_evaluate_intake";

export type MetadataStatus = "pending_hydration" | "complete" | "partial" | "missing" | "failed";

export type DouyinReupScoreLabel = "Excellent" | "Good" | "Average" | "Low" | "Needs metadata";
export type DouyinReupScoreLevel = "excellent" | "good" | "average" | "low" | "needs_metadata";
export type DouyinReupScoreComponents = {
  performance: number;
  engagement: number;
  virality_retention: number;
  duration_fit: number;
  recency: number;
  metadata_quality: number;
  penalty: number;
  outlier_bonus: number;
};

export type MetadataGroupStatus = "captured" | "missing" | "failed" | "pending";

export type CaptureInboxReconciliation = {
  visible_item_count: number;
  captured_item_count: number;
  normalized_item_count: number;
  duplicate_item_count: number;
  ready_item_count: number;
  skipped_item_count: number;
  promoted_item_count: number;
  candidate_created_count: number;
  failed_item_count: number;
};

export type IntakeEvaluationStatus = "NOT_EVALUATED" | "MATCHED" | "FILTERED_OUT" | "MISSING_REQUIREMENTS" | "EVALUATION_ERROR";

export type CapturedItem = {
  id: string;
  workspace_id: string;
  capture_session_id: string;
  source_platform: string;
  status: CapturedItemStatus;
  raw_item_index: number;
  source_profile_external_id: string | null;
  profile_url: string | null;
  source_video_external_id: string | null;
  aweme_id: string | null;
  source_url: string | null;
  share_url: string | null;
  caption: string | null;
  title: string | null;
  poster_aspect_ratio: number | null;
  duration_seconds: number | null;
  duration_text: string | null;
  posted_at: string | null;
  posted_text: string | null;
  posted_text_raw: string | null;
  posted_display: string | null;
  duration_text_raw?: string | null;
  duration_parse_confidence?: "high" | "medium" | "low" | "none";
  posted_parse_confidence?: "high" | "medium" | "low" | "none";
  thumbnail_url: string | null;
  video_url?: string | null;
  profile_name?: string | null;
  view_count: number | null;
  view_count_text: string | null;
  like_count: number | null;
  like_count_text: string | null;
  comment_count: number | null;
  comment_count_text: string | null;
  share_count: number | null;
  share_count_text: string | null;
  favorite_count?: number | null;
  favorite_count_text?: string | null;
  /** Author follower count when captured — required for Outlier Bonus scoring. */
  follower_count?: number | null;
  follower_count_text?: string | null;
  estimated_views_text_raw?: string | null;
  estimated_views_display?: string | null;
  estimated_views_min?: number | null;
  estimated_views_max?: number | null;
  estimated_views_mid?: number | null;
  estimated_views_parse_confidence?: "high" | "medium" | "low" | "none";
  engagement_rate: number | null;
  engagement_score?: number | null;
  engagement_rate_basis?: "estimated_views_mid" | "view_count" | "none";
  reup_score?: number | null;
  reup_score_label?: DouyinReupScoreLabel | null;
  reup_score_level?: DouyinReupScoreLevel | null;
  reup_score_components?: DouyinReupScoreComponents | null;
  reup_score_reasons?: string[] | null;
  preview_url: string | null;
  preview_status: "ready" | "pending" | "missing" | null;
  source_link_status: "captured" | "missing" | null;
  media_asset_status: "not_generated" | "ready" | "failed" | null;
  media_status: "ready" | "pending" | "missing" | "source_link_captured" | null;
  preview_ready: boolean;
  media_ready: boolean;
  readiness_reasons_json: unknown[] | null;
  dedupe_key: string | null;
  duplicate_of_item_id: string | null;
  existing_source_video_id: string | null;
  promoted_source_video_id: string | null;
  promoted_video_candidate_id: string | null;
  promoted_crawl_session_id: string | null;
  enrichment_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  thumbnail_source?: "network_json" | "dom_fallback" | "detail_hydrate" | "dom_snapshot" | "existing_canonical" | "profile_card" | "video_poster" | "profile_card_image" | "modal_img" | "og_image" | "missing" | null;
  posted_source?: "network_json" | "dom_text" | "detail_hydrate" | "dom_detail_modal" | "dom_snapshot" | "existing_canonical" | "fallback_none" | "missing" | "modal_author_row" | "direct_publish_time" | "embedded_aweme_json" | "profile_card" | null;
  duration_source?: "network_json" | "dom_text" | "detail_hydrate" | "dom_snapshot" | "existing_canonical" | "profile_card" | "fallback_none" | "missing" | null;
  view_count_source?: "network_json" | "dom_text" | "detail_hydrate" | "dom_snapshot" | "existing_canonical" | "profile_card" | "fallback_none" | "missing" | null;
  like_count_source?: "network_json" | "dom_text" | "detail_hydrate" | "dom_snapshot" | "existing_canonical" | "profile_card" | "fallback_none" | "missing" | null;
  comment_count_source?: "network_json" | "dom_text" | "detail_hydrate" | "dom_detail_modal" | "dom_snapshot" | "dom_zero_sentinel" | "existing_canonical" | "fallback_none" | "missing" | null;
  share_count_source?: "network_json" | "dom_text" | "detail_hydrate" | "dom_detail_modal" | "dom_snapshot" | "dom_zero_sentinel" | "existing_canonical" | "fallback_none" | "missing" | null;
  engagement_rate_source?: "derived" | "derived_from_counts" | "derived_from_canonical_counts" | "network_json" | "detail_hydrate" | "dom_text" | "dom_fallback" | "dom_snapshot" | "existing_canonical" | "fallback_none" | "missing" | null;
  raw_evidence_summary?: {
    has_network_aweme?: boolean;
    has_detail_aweme?: boolean;
    has_dom_snapshot?: boolean;
  } | null;
  metadata_status: MetadataStatus;
  time_status: MetadataGroupStatus;
  performance_status: MetadataGroupStatus;
  processing_fit_status: MetadataGroupStatus;
  metadata_missing_reason: string | null;
  time_missing_reason: string | null;
  performance_missing_reason: string | null;
  processing_fit_missing_reason: string | null;
  metadata_source_summary: string | null;
  last_metadata_hydrated_at: string | null;
  has_thumbnail?: boolean;
  has_posted?: boolean;
  has_duration?: boolean;
  has_views?: boolean;
  has_likes?: boolean;
  has_comments?: boolean;
  has_shares?: boolean;
  has_all_core_metadata?: boolean;
  missing_metadata_fields?: string[];
  has_speech?: boolean | null;
  text_density?: "low" | "medium" | "high" | null;
  has_heavy_watermark?: boolean | null;
  processing_complexity?: "low" | "medium" | "high" | null;
  copyright_risk?: "low" | "medium" | "high" | null;
  intake_evaluation_status: IntakeEvaluationStatus;
  matches_intake: boolean | null;
  intake_failed_rules_json: string[] | null;
  intake_missing_requirements_json: string[] | null;
  intake_filter_version: string | null;
  intake_preset_name: string | null;
  last_intake_evaluated_at: string | null;
  intake_evaluation_error: string | null;
  excluded_reason: string | null;
  error_code: string | null;
  error_message: string | null;
  raw_payload_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type CaptureSession = {
  id: string;
  workspace_id: string;
  capture_id: string | null;
  source_platform: string;
  capture_source: string;
  status: CaptureSessionStatus;
  detected_page_type: string | null;
  page_url: string | null;
  page_title: string | null;
  submitted_profile_url: string | null;
  normalized_profile_identifier: string | null;
  visible_item_count: number;
  captured_item_count: number;
  normalized_item_count: number;
  duplicate_item_count: number;
  ready_item_count: number;
  skipped_item_count: number;
  promoted_item_count: number;
  candidate_created_count: number;
  failed_item_count: number;
  started_at: string | null;
  finished_at: string | null;
  diagnostics_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  raw_summary_json: Record<string, unknown> | null;
  result_summary_json: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
};

export type CaptureSessionDetail = CaptureSession & {
  items: CapturedItem[];
  reconciliation: CaptureInboxReconciliation;
};

export type CaptureSessionCounts = {
  captured: number;
  ready: number;
  needs_action?: number;
  dup: number;
  fail: number;
};

export type CaptureInboxProfileSummaryResponse = {
  profile_identifier: string;
  normalized_profile_url: string;
  profile_scope: "same_profile_only";
  source: "capture_inbox_profile_summary";
  total_count: number;
  unique_video_count: number;
  counts: CaptureSessionCounts;
};

export type CaptureInboxProfileItemsResponse = {
  profile_identifier: string;
  normalized_profile_url: string;
  profile_scope: "same_profile_only";
  source: "capture_inbox_profile_items";
  total_count: number;
  unique_video_count: number;
  offset: number;
  items_count: number;
  counts: CaptureSessionCounts;
  items: CapturedItem[];
};

export type CaptureSessionItemsBySessionResponse = {
  session_id: string;
  items_count: number;
  items: CapturedItem[];
  counts: CaptureSessionCounts;
};

export type CaptureSessionListResponse = {
  sessions: CaptureSession[];
  total_count: number;
};

export type CapturedItemListResponse = {
  items: CapturedItem[];
  total_count: number;
  status_counts: Record<StudioItemStatusFilter, number>;
};

export type CaptureInboxAdvancedFilter = {
  from_date?: string;
  to_date?: string;
  min_views?: number;
  max_views?: number;
  min_likes?: number;
  max_likes?: number;
  min_comments?: number;
  max_comments?: number;
  min_shares?: number;
  max_shares?: number;
  min_engagement_rate?: number;
  max_engagement_rate?: number;
  min_duration_seconds?: number;
  max_duration_seconds?: number;
  speech?: boolean;
  max_text_density?: "low" | "medium" | "high";
  exclude_heavy_watermark?: boolean;
  exclude_high_complexity?: boolean;
  exclude_high_processing_complexity?: boolean;
  exclude_high_copyright_risk?: boolean;
};

export type CaptureInboxItemQueryRequest = {
  capture_session_id: string;
  status?: CapturedItemStatus;
  studio_status?: StudioItemStatusFilter;
  search?: string;
  limit?: number;
  offset?: number;
  advanced_filter?: CaptureInboxAdvancedFilter;
};

export type CaptureInboxActionRequest = {
  action: CaptureInboxAction;
  item_ids?: string[];
  preset_name?: string | null;
  persist?: boolean;
  exclude_reason?: string | null;
};

export type CaptureInboxActionItemResult = {
  item_id: string;
  reason: string;
};

export type CaptureInboxActionResponse = {
  success: boolean;
  action: string;
  capture_session_id: string | null;
  affected_item_ids: string[];
  promoted_item_count: number;
  candidate_created_count: number;
  message: string;
  session: CaptureSession | null;
  items: CapturedItem[];
  skipped: CaptureInboxActionItemResult[];
  failed: CaptureInboxActionItemResult[];
  raw_details: Array<Record<string, unknown>>;
  source_urls: string[];
};
