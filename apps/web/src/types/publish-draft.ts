export type PublishTargetPlatform = "TIKTOK" | "FACEBOOK_REELS" | "YOUTUBE_SHORTS";
export type PublishDraftStatus =
  | "DRAFT"
  | "READY"
  | "SCHEDULED"
  | "PUBLISHING"
  | "PUBLISHED"
  | "FAILED"
  | "NEEDS_ATTENTION"
  | "ARCHIVED";
export type PlatformAccountStatus = "ACTIVE" | "PAUSED" | "INVALID" | "ARCHIVED";
export type PublishAccountAssignmentStatus = "UNASSIGNED" | "ASSIGNED" | "OVERRIDDEN";
export type PlatformAccountHealthStatus = "HEALTHY" | "DEGRADED" | "UNHEALTHY" | "HELD";
export type PublishAttemptStatus =
  | "QUEUED"
  | "RUNNING"
  | "UPLOADING"
  | "PUBLISHING"
  | "AWAITING_PLATFORM_CONFIRMATION"
  | "SUCCEEDED"
  | "FAILED"
  | "NEEDS_RECONCILIATION"
  | "RECONCILING"
  | "RECONCILED"
  | "CANCELLED";
export type ExternalPublicationStatus =
  | "UNKNOWN"
  | "PROCESSING"
  | "PUBLISHED"
  | "FAILED"
  | "REMOVED"
  | "NOT_FOUND"
  | "PARTIALLY_CONFIRMED";
export type PublishReconciliationStatus =
  | "NOT_REQUIRED"
  | "REQUIRED"
  | "IN_PROGRESS"
  | "RESOLVED_SUCCESS"
  | "RESOLVED_FAILURE"
  | "UNRESOLVED";

export type HashtagDraftItem = {
  tag: string;
  source: string;
};

export type PublishTarget = {
  platform: PublishTargetPlatform;
  label: string;
  caption_max_length: number;
  hashtag_limit: number;
  supports_scheduling: boolean;
  account_ref_required: boolean;
};

export type PublishDraft = {
  id: string;
  workspace_id: string;
  source_video_id: string;
  render_output_id: string | null;
  target_platform: PublishTargetPlatform;
  platform_account_ref: string | null;
  version: number;
  status: PublishDraftStatus;
  title: string | null;
  caption: string | null;
  cta_text: string | null;
  language_code: string | null;
  hashtags_json: HashtagDraftItem[] | null;
  caption_draft_json: Record<string, unknown> | null;
  cta_draft_json: Record<string, unknown> | null;
  schedule_json: Record<string, unknown> | null;
  planned_publish_at: string | null;
  timezone: string | null;
  scheduled_at: string | null;
  ready_at: string | null;
  generation_source: string | null;
  platform_payload_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  platform_notes: string | null;
  scheduling_notes: string | null;
  notes: string | null;
  error_message: string | null;
  canonical_publish_attempt_id: string | null;
  latest_publish_attempt_id: string | null;
  current_publication_status: ExternalPublicationStatus | null;
  current_external_publish_id: string | null;
  current_external_permalink: string | null;
  published_at: string | null;
  last_publish_synced_at: string | null;
  publication_summary_json: Record<string, unknown> | null;
  assigned_platform_account_id: string | null;
  assignment_status: PublishAccountAssignmentStatus | null;
  assigned_at: string | null;
  assigned_reason: string | null;
  assigned_by: string | null;
  assignment_metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type PublishDraftListResponse = {
  drafts: PublishDraft[];
};

export type PlatformAccount = {
  id: string;
  workspace_id: string;
  platform: PublishTargetPlatform;
  display_name: string;
  external_account_id: string;
  token_reference: string | null;
  status: PlatformAccountStatus;
  priority: number;
  is_on_hold: boolean;
  hold_reason: string | null;
  cooldown_until: string | null;
  allowed_niches_json: unknown[] | null;
  metadata_json: Record<string, unknown> | null;
  routing_notes: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type PlatformAccountListResponse = {
  accounts: PlatformAccount[];
};

export type PublishAttempt = {
  id: string;
  workspace_id: string;
  publish_draft_id: string;
  platform: PublishTargetPlatform;
  platform_account_id: string;
  attempt_number: number;
  status: PublishAttemptStatus;
  started_at: string | null;
  finished_at: string | null;
  external_publish_id: string | null;
  external_media_id: string | null;
  external_reel_id: string | null;
  external_permalink: string | null;
  external_status: ExternalPublicationStatus | null;
  reconciliation_status: PublishReconciliationStatus | null;
  reconciliation_required: boolean;
  last_status_checked_at: string | null;
  last_status_sync_result_json: Record<string, unknown> | null;
  request_summary_json: Record<string, unknown> | null;
  response_summary_json: Record<string, unknown> | null;
  warning_summary_json: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  created_by_job_id: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type PublishAttemptListResponse = {
  attempts: PublishAttempt[];
};

export type PublicationSummary = {
  publish_draft_id: string;
  draft_status: PublishDraftStatus;
  current_publication_status: ExternalPublicationStatus;
  canonical_publish_attempt_id: string | null;
  latest_publish_attempt_id: string | null;
  current_external_publish_id: string | null;
  current_external_permalink: string | null;
  published_at: string | null;
  last_publish_synced_at: string | null;
  attempt_count: number;
  active_attempt_count: number;
  needs_reconciliation_count: number;
  duplicate_success_count: number;
  requires_operator_attention: boolean;
  warnings: string[];
};

export type PublishHistoryResponse = {
  publish_draft_id: string;
  summary: PublicationSummary;
  attempts: PublishAttempt[];
  canonical_attempt: PublishAttempt | null;
  latest_attempt: PublishAttempt | null;
};

export type EditablePublishDraft = {
  id: string;
  targetPlatform: PublishTargetPlatform;
  platformAccountRef: string;
  title: string;
  caption: string;
  ctaText: string;
  hashtags: HashtagDraftItem[];
  languageCode: string;
  platformNotes: string;
  schedulingNotes: string;
  notes: string;
  plannedPublishAt: string;
  timezone: string;
};
