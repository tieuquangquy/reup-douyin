import type { IntakeDateChip } from "../lib/reviewBoardIntake";

export type ReviewCandidateCanonicalFields = {
  capture_item_id?: string | null;
  capture_session_id?: string | null;
  source?: string | null;
  source_module?: string | null;
  aweme_id?: string | null;
  source_video_external_id?: string | null;
  source_url?: string | null;
  video_url?: string | null;
  profile_url?: string | null;
  profile_name?: string | null;
  caption?: string | null;
  title?: string | null;
  description?: string | null;
  thumbnail_url?: string | null;
  thumbnail?: string | null;
  posted_at?: string | null;
  posted_display_exact?: string | null;
  posted_display?: string | null;
  posted?: string | null;
  posted_text?: string | null;
  posted_text_raw?: string | null;
  postedDisplay?: string | null;
  duration_seconds?: number | null;
  durationSeconds?: number | null;
  duration_text?: string | null;
  durationText?: string | null;
  duration?: string | null;
  view_count?: number | null;
  view_count_text?: string | null;
  estimated_views_text_raw?: string | null;
  estimated_views_display?: string | null;
  views_display?: string | null;
  estimated_views_min?: number | null;
  estimated_views_max?: number | null;
  estimated_views_mid?: number | null;
  views_mid?: number | null;
  estimated_views_parse_confidence?: string | null;
  like_count?: number | null;
  likes?: number | null;
  like_count_text?: string | null;
  comment_count?: number | null;
  comments?: number | null;
  comment_count_text?: string | null;
  share_count?: number | null;
  shares?: number | null;
  share_count_text?: string | null;
  favorite_count?: number | null;
  favorite_count_text?: string | null;
  engagement_score?: number | null;
  engagement_rate?: number | null;
  reup_score?: number | null;
  reup_score_label?: string | null;
  reup_score_level?: string | null;
  reup_score_components?: Record<string, unknown> | null;
  reup_score_reasons?: string[] | null;
  review_status?: string | null;
  decision_status?: string | null;
  preset?: string | null;
  matched_presets?: string[] | null;
  has_thumbnail?: boolean | null;
  has_posted?: boolean | null;
  has_duration?: boolean | null;
  has_estimated_views?: boolean | null;
  has_likes?: boolean | null;
  has_comments?: boolean | null;
  has_shares?: boolean | null;
  has_all_core_metadata?: boolean | null;
  missing_metadata_fields?: string[] | null;
  source_metadata?: Record<string, unknown> | null;
  capture_to_review_comparison?: Record<string, unknown> | null;
};

export type CandidateStatus =
  | "NEW"
  | "SHORTLISTED"
  | "IN_REVIEW"
  | "APPROVED"
  | "REJECTED"
  | "ARCHIVED";

export type ScoreLabel = "hot" | "usable" | "skip" | string;

export type SourceVideoSummary = {
  id: string;
  source_profile_id: string;
  source_video_external_id: string;
  source_url: string;
  caption: string | null;
  posted_at: string | null;
  duration_seconds: number | null;
  metadata_json: Record<string, unknown> | null;
};

export type ReviewCandidateDebug = {
  traceVersion: string;
  apiEndpoint: string;
  candidateId: string;
  captureItemId: string | null;
  awemeId: string | null;
  hydrationAttempted?: boolean;
  hydrated?: boolean;
  hydrationMatchKey?: string | null;
  hydrationCaptureItemId?: string | null;
  hydrationUpdatedFields?: string[];
  hydrationReasonIfSkipped?: string | null;
  hydration_lookup?: Record<string, unknown> | null;
  visibleScore: number | null;
  visibleScoreSource: string;
  scoreSource?: string;
  scoreValue?: number | null;
  rawCandidateScore: number | null;
  rawCandidateReupScore: number | null;
  rawCandidatePriorityScore: number | null;
  estimatedViewsSource: string;
  estimatedViewsDisplay: string | null;
  metricsSource?: string;
  likeCount: number | null;
  commentCount: number | null;
  shareCount: number | null;
  postedDisplay: string | null;
  postedDisplaySource?: string | null;
  postedDisplayValue?: string | null;
  postedAtValue?: string | null;
  postedDisplayExactValue?: string | null;
  postedDisplayWasFormatted?: boolean;
  durationText: string | null;
  durationSource?: string | null;
  durationValue?: string | number | null;
  sourceMetadataPresent: boolean;
  sourceMetadataVersion?: string | null;
  capture_to_review_comparison?: Record<string, unknown> | null;
  candidateMetadataKeys?: string[];
  sourceMetadataKeys?: string[];
  rawCandidateKeys: string[];
};

export type Candidate = ReviewCandidateCanonicalFields & {
  id: string;
  source_video_id: string;
  status: CandidateStatus;
  score: number | null;
  score_version: string | null;
  score_label: ScoreLabel | null;
  score_breakdown_json: ScoreBreakdown | null;
  score_reason: string | null;
  preset_name: string | null;
  filter_config_json: Record<string, unknown> | null;
  inclusion_reasons_json: string[] | null;
  exclusion_reasons_json: string[] | null;
  warnings_json: string[] | null;
  evaluated_at: string | null;
  priority: number;
  metadata_json: Record<string, unknown> | null;
  review_board_trace_version?: string | null;
  review_candidate_debug?: ReviewCandidateDebug | null;
  review_board_api_debug?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
  in_reup_queue?: boolean;
  reup_queue_item_id?: string | null;
  reup_queue_status?: string | null;
  source_video: SourceVideoSummary | null;
};

export type ScoreComponent = {
  raw_input: Record<string, unknown>;
  normalized_subscore: number;
  weight: number;
  weighted_contribution: number;
};

export type ScoreBreakdown = Record<string, ScoreComponent>;

export type CandidateSummary = {
  id: string;
  source_video_id: string;
  status: CandidateStatus;
  score: number | null;
  score_label: ScoreLabel | null;
  priority: number;
  preset_name: string | null;
  reup_score?: number | null;
  caption?: string | null;
  thumbnail_url?: string | null;
  posted_display?: string | null;
  duration_text?: string | null;
  estimated_views_display?: string | null;
  estimated_views_min?: number | null;
  estimated_views_max?: number | null;
  estimated_views_mid?: number | null;
  like_count?: number | null;
  comment_count?: number | null;
  share_count?: number | null;
  engagement_rate?: number | null;
  duration_seconds?: number | null;
  aweme_id?: string | null;
  source_video_external_id?: string | null;
  source_url?: string | null;
  review_status?: string | null;
  decision_status?: string | null;
  updated_at: string;
  evaluated_at?: string | null;
  in_reup_queue?: boolean;
  reup_queue_item_id?: string | null;
  reup_queue_status?: string | null;
  source_video: SourceVideoSummary | null;
};

export type CandidateListResponse = {
  view: "summary" | "detail";
  total_count: number;
  status_counts: Partial<Record<CandidateStatus, number>>;
  offset: number;
  limit: number;
  candidates: CandidateSummary[] | Candidate[];
  review_board_trace_version?: string;
  review_board_api_debug?: Record<string, unknown> | null;
  review_board_hydration_summary?: Record<string, unknown> | null;
};

export type CandidateDeleteResponse = {
  candidate: Candidate;
  message: string;
};

export type FilterPreset = {
  name: string;
  description: string;
  use_when: string;
  filter_config: Record<string, unknown>;
  score_weights: Record<string, number>;
};

export type FilterPresetListResponse = {
  presets: FilterPreset[];
};

export type CandidateFilters = {
  status: CandidateStatus | "";
  minScore: string;
  maxScore: string;
  sourceProfileId: string;
  search: string;
  sort: "score_desc" | "newest_first" | "views_desc";
  presetName: string;
  captureSessionId: string;
  dateChip: IntakeDateChip;
  dateFrom: string;
  dateTo: string;
};

export type BulkActionStatus = "APPROVED" | "REJECTED" | "IN_REVIEW";

