import type { PublishDraftStatus, PublishTargetPlatform } from "./publish-draft";

export type AnalyticsWindow = "today" | "last_7_days" | "last_30_days";
export type ExternalPublicationStatus = "UNKNOWN" | "PROCESSING" | "PUBLISHED" | "FAILED" | "REMOVED" | "NOT_FOUND" | "PARTIALLY_CONFIRMED";
export type OperatorFeedbackTargetType = "SOURCE_VIDEO" | "RENDER_OUTPUT" | "PUBLISH_DRAFT" | "PUBLISH_ATTEMPT";
export type OperatorFeedbackQualityLabel = "GOOD" | "ACCEPTABLE" | "WEAK";
export type PublishConfidenceLabel = "SCALABLE" | "NEEDS_IMPROVEMENT" | "DO_NOT_REUSE_PATTERN";
export type OperatorFeedbackRootCause =
  | "SOURCE_SELECTION_ISSUE"
  | "TRANSCRIPT_QUALITY_ISSUE"
  | "TTS_ISSUE"
  | "SUBTITLE_ISSUE"
  | "RENDER_ISSUE"
  | "PUBLISH_ISSUE"
  | "RISK_FALSE_POSITIVE"
  | "CTA_CAPTION_ISSUE"
  | "OTHER";

export type PublishHealthOverview = {
  total_attempts: number;
  succeeded_attempts: number;
  failed_attempts: number;
  needs_reconciliation_attempts: number;
  canonical_published_count: number;
  drafts_ready_not_published: number;
  drafts_blocked_by_risk: number;
  success_rate_percent: number;
};

export type PublishDayStats = {
  day: string;
  attempts: number;
  succeeded: number;
  failed: number;
  needs_reconciliation: number;
};

export type AccountHealthSummary = {
  platform_account_id: string | null;
  display_name: string;
  platform: PublishTargetPlatform | string;
  attempts: number;
  succeeded: number;
  failed: number;
  needs_reconciliation: number;
  success_rate_percent: number;
  recent_error_code: string | null;
};

export type FailureCategorySummary = {
  error_code: string;
  count: number;
  label: string;
};

export type PublicationOutcomeItem = {
  publish_draft_id: string;
  source_video_id: string;
  render_output_id: string | null;
  platform: string;
  status: PublishDraftStatus;
  external_status: ExternalPublicationStatus;
  external_publish_id: string | null;
  external_permalink: string | null;
  canonical_publish_attempt_id: string | null;
  platform_account_id: string | null;
  source_profile_name: string | null;
  preset_name: string | null;
  niche_label: string | null;
  score: number | null;
  published_at: string | null;
  last_publish_synced_at: string | null;
  feedback_quality_label: OperatorFeedbackQualityLabel | null;
  feedback_confidence: PublishConfidenceLabel | null;
};

export type PipelineFeedbackGroup = {
  group_key: string;
  label: string;
  published_count: number;
  good_feedback_count: number;
  weak_feedback_count: number;
  needs_reconciliation_count: number;
  average_score: number | null;
};

export type PublishHealthDashboard = {
  generated_at: string;
  window: AnalyticsWindow;
  window_start: string;
  window_end: string;
  overview: PublishHealthOverview;
  by_day: PublishDayStats[];
  account_health: AccountHealthSummary[];
  failure_categories: FailureCategorySummary[];
  action_queue: {
    needs_reconciliation: PublicationOutcomeItem[];
    drafts_ready: PublicationOutcomeItem[];
    blocked_by_risk_count: number;
    recent_successes: PublicationOutcomeItem[];
  };
  pipeline_feedback: {
    by_source_profile: PipelineFeedbackGroup[];
    by_niche: PipelineFeedbackGroup[];
    by_preset: PipelineFeedbackGroup[];
  };
};

export type OperatorFeedbackPayload = {
  target_type: OperatorFeedbackTargetType;
  target_id: string;
  quality_label: OperatorFeedbackQualityLabel;
  publish_confidence: PublishConfidenceLabel;
  root_cause: OperatorFeedbackRootCause | null;
  note: string | null;
  created_by?: string;
};
