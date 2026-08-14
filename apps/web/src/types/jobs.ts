export type JobStatus =
  | "QUEUED"
  | "RUNNING"
  | "WAITING_FOR_REVIEW"
  | "RETRYABLE"
  | "FAILED"
  | "CANCELLED"
  | "COMPLETED";

export type JobType =
  | "CRAWL_PROFILE"
  | "SCORE_CANDIDATES"
  | "DOWNLOAD_VIDEO"
  | "ANALYZE_AUDIO"
  | "ANALYZE_OCR"
  | "BUILD_TRANSLATION_DRAFT"
  | "SYNTHESIZE_TTS"
  | "RENDER_PREVIEW"
  | "RENDER_FINAL"
  | "PUBLISH_CONTENT"
  | "REFRESH_PUBLISH_STATUS"
  | "RECONCILE_PUBLISH_ATTEMPT"
  | "COLLECT_PUBLICATION_METRICS"
  | "CLASSIFY_CONTENT"
  | string;

export type JobStep = {
  id: string;
  step_key: string;
  step_name: string;
  step_order: number;
  status: string;
  progress_percent: number;
  attempts: number;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  output_json: Record<string, unknown> | null;
};

export type Job = {
  id: string;
  workspace_id: string;
  job_type: JobType;
  workflow_action?: string | null;
  status: JobStatus;
  source_video_id: string | null;
  crawl_session_id: string | null;
  render_output_id: string | null;
  reference_type: string | null;
  reference_id: string | null;
  current_step_key: string | null;
  current_step_index: number;
  progress_percent: number;
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  priority: number;
  attempts: number;
  max_attempts: number;
  retryable: boolean;
  locked_by?: string | null;
  locked_at?: string | null;
  started_at: string | null;
  finished_at: string | null;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  steps: JobStep[];
};

export type JobListResponse = {
  jobs: Job[];
  total_count: number;
  limit: number;
  offset: number;
};
