import type { SourceVideoSummary } from "./review-board";

export type ReupQueueStatus =
  | "READY_FOR_PROCESSING"
  | "WAITING_FOR_MEDIA"
  | "WAITING_FOR_METADATA"
  | "PROCESSING"
  | "READY_TO_EXPORT"
  | "EXPORT_PACKAGE_CREATED"
  | "READY_TO_PUBLISH"
  | "PUBLISH_HANDOFF_CREATED"
  | "FAILED_NEEDS_ATTENTION"
  | "COMPLETED"
  | "CANCELLED";

export type ReupQueueAction =
  | "START_PROCESSING"
  | "START_AUTO_PIPELINE"
  | "SET_AUTOMATION"
  | "MARK_MEDIA_READY"
  | "MARK_BLOCKED"
  | "HOLD"
  | "RESUME"
  | "RETRY"
  | "CANCEL"
  | "MARK_COMPLETED"
  | "DISMISS";

export type ReupQueueMediaPrepStatus =
  | "NOT_STARTED"
  | "WAITING_FOR_MEDIA"
  | "WAITING_FOR_METADATA"
  | "READY_FOR_EXPORT"
  | "BLOCKED";

export type ReupQueueAvailableAction = {
  action: ReupQueueAction;
  label: string;
  description: string;
  requires_note: boolean;
};

export type ReupQueueItem = {
  id: string;
  workspace_id: string;
  video_candidate_id: string;
  source_video_id: string;
  status: ReupQueueStatus;
  bucket: string;
  next_action: string;
  priority: number;
  queued_reason: string | null;
  operator_note: string | null;
  last_error_code: string | null;
  last_error_message: string | null;
  media_prep_status: ReupQueueMediaPrepStatus;
  media_prep_notes: string | null;
  media_ready_at: string | null;
  blocked_reason: string | null;
  blocked_at: string | null;
  held_at: string | null;
  failed_at: string | null;
  last_action: ReupQueueAction | null;
  last_action_at: string | null;
  last_action_note: string | null;
  available_actions: ReupQueueAvailableAction[];
  queued_at: string | null;
  started_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  operator_dismissed_at?: string | null;
  job_id: string | null;
  job_type?: string | null;
  job_status?: string | null;
  job_progress_percent?: number | null;
  job_phase?: string | null;
  job_phase_current?: number | null;
  job_phase_total?: number | null;
  job_error_code?: string | null;
  job_error_message?: string | null;
  render_output_id: string | null;
  publish_draft_id: string | null;
  metadata_json: Record<string, unknown> | null;
  source_video: SourceVideoSummary | null;
  /** From ANALYZE_AUDIO — worklist branches Transcript vs No dialogue. */
  has_speech?: boolean | null;
  dialogue_phase?: string | null;
  transcript_count?: number | null;
  created_at: string;
  updated_at: string;
};

export type ReupQueueListResponse = {
  items: ReupQueueItem[];
  total_count: number;
  limit: number;
  offset: number;
  status_counts?: Record<string, number>;
};

export type ReupQueueActionRequest = {
  action: ReupQueueAction;
  note?: string | null;
  blocked_reason?: string | null;
  media_prep_notes?: string | null;
  media_prep_status?: ReupQueueMediaPrepStatus | null;
  /** START_AUTO_PIPELINE: stop after TTS, or continue through OCR and final render. */
  pipeline_mode?: string | null;
  expected_stage_versions?: Record<string, string> | null;
};

export type ReupQueueActionResponse = {
  item: ReupQueueItem;
};

export type ReupQueueEnqueueRequest = {
  candidate_ids: string[];
  priority?: number;
  queued_reason?: string | null;
  operator_note?: string | null;
};

export type ReupQueueEnqueueResponse = {
  requested_count: number;
  queued_count: number;
  already_queued_count: number;
  skipped_count: number;
  items: ReupQueueItem[];
  skipped_candidate_ids: string[];
};
