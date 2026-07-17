import {
  normalizeDouyinCalibration,
  type DouyinCalibrationLayout,
  type DouyinCalibrationPointName,
  type DouyinCalibrationSource,
  REQUIRED_DOUYIN_CALIBRATION_POINTS
} from "./calibration.js";

export const WHOLE_PROFILE_HARVEST_STATE_KEY = "douyinWholeProfileHarvest";
export const WHOLE_PROFILE_HARVEST_SCHEMA_VERSION = "phase18i_a_three_layer_harvest_design";

export type WholeProfileHarvestStatus = "idle" | "verifying" | "verified" | "dry_running" | "harvest_ready" | "harvesting" | "paused" | "completed" | "failed";
export type WholeProfileHarvestMode = "new_and_incomplete" | "new_only" | "refresh_all";
export type WholeProfileHarvestSpeed = "safe" | "normal" | "fast";
export type WholeProfileHarvestQueueStatus = "new" | "pending" | "processing" | "retry" | "incomplete" | "needs_metadata" | "failed_recoverable" | "extracted" | "backend_verified" | "complete" | "already_collected" | "duplicate" | "skipped" | "failed" | "failed_permanent";
export type WholeProfileHarvestRunStatus = "idle" | "queue_ready" | "running" | "paused" | "completed" | "completed_with_warnings" | "failed";
export type WholeProfileHarvestBatch = "next_5" | "next_10" | "next_20" | "all_remaining";
export type WholeProfileHarvestCaptureStatus = "unknown" | "new" | "incomplete" | "complete" | "failed" | "skipped";
export type WholeProfileHarvestCalibrationStatus = "unknown" | "missing" | "needed" | "calibrated";
export type WholeProfileHarvestVerifyStatus = "idle" | "running" | "success" | "failed";
export type DouyinScannerWorkflowStatus = "idle" | "running" | "success" | "failed";
export type DouyinScannerCollectionStatus = "idle" | "opening_target" | "running" | "pausing" | "paused" | "success" | "failed";
export type DouyinScannerActiveTask = null | "scan_profile" | "classify_profile" | "collect_videos";
export type PersistentCollectJobState = "idle" | "starting" | "running" | "running_tab_inactive" | "waiting_for_active_tab" | "paused_tab_inactive" | "recovering" | "start_failed_recoverable" | "start_blocked_tab_inactive" | "recoverable_stuck" | "paused_stale_recovered" | "aborted_by_user_fix_stuck" | "completed" | "failed" | "stuck";
export type PersistentScanJobStatus = "idle" | "running" | "paused" | "retry_wait" | "completed" | "failed";
export type PersistentScanHasMoreState = boolean | null;
export type PersistentScanJobRecord = {
  scan_job_id: string | null;
  status: PersistentScanJobStatus;
  profile_identifier: string | null;
  cursor: string | number | null;
  has_more_state: PersistentScanHasMoreState;
  page_count: number;
  request_count: number;
  last_http_status: number | null;
  last_status_code: number | string | null;
  last_error: string | null;
  started_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
  next_retry_at: string | null;
  retry_count: number;
  resume_source: "new" | "resume_existing" | null;
  continuation_cursor_source?: "fresh_start" | "saved_continuation_checkpoint" | "replay_recovery_checkpoint" | "unknown" | null;
  continuation_resume_strategy?: "fresh_scan" | "resume_from_saved_cursor" | "replay_recovery_from_saved_cursor" | "none" | null;
  continuation_resume_result?: "not_started" | "resumed_from_saved_cursor" | "replay_recovery_resumed" | "checkpoint_unavailable" | "not_applicable" | null;
  continuation_replay_duplicate_pages_detected?: "yes" | "no" | null;
  continuation_replay_duplicate_count?: number | null;
  continuation_recovery_attempted?: "yes" | "no" | null;
  continuation_recovery_result?: "not_attempted" | "reused_saved_cursor" | "checkpoint_unavailable" | "recovery_exhausted" | null;
  continuation_checkpoint_id?: string | null;
  continuation_run_id?: string | null;
  continuation_persisted_total?: number | null;
  continuation_progress_total?: number | null;
  current_run_new_inserted_total?: number | null;
  current_run_duplicate_existing_total?: number | null;
  consecutive_no_new_pages: number;
  total_discovered: number;
  total_persisted: number;
  expected_count: number | null;
  remaining_estimate: number | null;
};
export type PersistentCollectJobRecord = {
  job_id: string | null;
  profile_identifier: string | null;
  normalized_profile_identifier: string | null;
  state: PersistentCollectJobState;
  started_at: string | null;
  updated_at: string | null;
  heartbeat_at: string | null;
  completed_at: string | null;
  runner_ack_at: string | null;
  startup_deadline_at: string | null;
  startup_timeout_ms: number | null;
  failure_reason: string | null;
  last_error: string | null;
  current_step: string | null;
  current_aweme_id: string | null;
  current_item_index: number | null;
  batch_limit: number | null;
  job_type?: "batch_collect" | "one_item_collect" | null;
  selected_count: number;
  selected_aweme_ids?: string[];
  selected_indexes?: number[];
  start_index?: number | null;
  runtime_generation?: number | null;
  attempted_count: number;
  succeeded_count: number;
  failed_count: number;
  skipped_count: number;
  pre_batch_backend_captured: number | null;
  pre_batch_backend_ready: number | null;
  pre_batch_backend_dup: number | null;
  pre_batch_backend_fail: number | null;
  pre_batch_new: number | null;
  pre_batch_queue: number | null;
  post_batch_backend_captured: number | null;
  post_batch_backend_ready: number | null;
  post_batch_backend_dup: number | null;
  post_batch_backend_fail: number | null;
  post_batch_new: number | null;
  post_batch_queue: number | null;
  batch_delta_captured: number | null;
  batch_delta_queue: number | null;
  lock_owner: string | null;
  lock_acquired_at: string | null;
  lock_expires_at: string | null;
  recoverable: boolean;
  stale_reason: string | null;
  heartbeat_updates_count: number;
  lock_released: boolean;
};
export type ActiveCollectRuntimeCanonicalState = "idle" | "starting" | "running" | "waiting_for_modal" | "waiting_for_extract" | "waiting_for_backend_write" | "waiting_for_post_batch_summary" | "waiting_for_active_tab" | "paused_tab_inactive" | "recoverable_stuck" | "start_failed_recoverable" | "completed" | "failed";
export type ActiveCollectRuntimeTraceBlock = {
  active_runner_trace: Record<string, unknown> | null;
  popup_render_trace: Record<string, unknown> | null;
  stale_check_trace: Record<string, unknown> | null;
  recovery_trace: Record<string, unknown> | null;
  queue_filtering: Record<string, unknown> | null;
  per_item_backend_writes: Record<string, unknown> | null;
  timing: Record<string, unknown> | null;
  summary: Record<string, unknown> | null;
};
export type ActiveCollectRuntimeRecord = {
  job_id: string | null;
  runtime_version: string;
  runtime_generation: number;
  render_generation: number;
  canonical_state: ActiveCollectRuntimeCanonicalState;
  canonical_phase: string | null;
  current_step: string | null;
  current_aweme_id: string | null;
  current_item_index: number | null;
  batch_limit: number | null;
  selected_count: number;
  attempted_count: number;
  succeeded_count: number;
  failed_count: number;
  skipped_count: number;
  pre_batch_backend_captured: number | null;
  pre_batch_backend_ready: number | null;
  pre_batch_backend_dup: number | null;
  pre_batch_backend_fail: number | null;
  pre_batch_new: number | null;
  pre_batch_queue: number | null;
  latest_progress_captured: number | null;
  latest_progress_queue: number | null;
  latest_progress_new: number | null;
  heartbeat_at: string | null;
  lock_owner: string | null;
  lock_expires_at: string | null;
  last_update_source: string | null;
  last_update_writer: string | null;
  writer_epoch_ms: number | null;
  writer_conflict_rejected: boolean;
  stale_write_rejected: boolean;
  rejected_update_source: string | null;
  rejected_update_generation: number | null;
  trace: ActiveCollectRuntimeTraceBlock;
  updated_at: string | null;
};
export type DouyinScannerWorkflowStep = {
  status: DouyinScannerWorkflowStatus;
  started_at: string | null;
  updated_at: string | null;
  completed_at: string | null;
  last_error: string | null;
};
export type DouyinScannerCollectionStep = Omit<DouyinScannerWorkflowStep, "status"> & { status: DouyinScannerCollectionStatus };
export type DouyinScannerWorkflowState = {
  scan: DouyinScannerWorkflowStep;
  classification: DouyinScannerWorkflowStep;
  collection: DouyinScannerCollectionStep;
  active_task: DouyinScannerActiveTask;
  action_lock: string | null;
};
export type WholeProfileHarvestDryRunStatus = "idle" | "running" | "success" | "completed_with_warnings" | "failed";
export type WholeProfileHarvestDryRunMode = "first" | "last" | "random";

export type WholeProfileHarvestPageContext = {
  page_type: string | null;
  current_url: string | null;
  modal_id: string | null;
  content_script_status: string | null;
  detector_status: string | null;
  modal_transition: unknown | null;
};

export type WholeProfileHarvestCalibration = {
  status: WholeProfileHarvestCalibrationStatus;
  ready?: boolean;
  layout?: DouyinCalibrationLayout;
  source_url?: string | null;
  profile_url?: string | null;
  aweme_id?: string | null;
  source?: DouyinCalibrationSource;
  updated_at?: string | null;
  points?: Record<string, unknown>;
  point_count: number;
  missing_points?: DouyinCalibrationPointName[];
  migrated_from_legacy?: boolean;
  storage_keys_checked_count?: number | null;
  source_key: string | null;
  viewport_warning: string | null;
};

export type WholeProfileHarvestBackendItem = {
  item_id: string | null;
  metadata_status: string | null;
  missing_fields: string[];
  existing_fields: Record<string, boolean>;
  updated_at: string | null;
};

export type WholeProfileHarvestTargetDetail = {
  index: number;
  aweme_id: string;
  source_url: string | null;
  profile_url: string | null;
  thumbnail_url: string | null;
  title: string | null;
  caption: string | null;
  text_sample: string | null;
  posted_text: string | null;
  posted_at: string | null;
  duration_text: string | null;
  duration_seconds: number | null;
  view_text: string | null;
  view_count: number | null;
  candidate_validation: {
    status: "accepted";
    source: "video_link" | "modal_link" | "data_attr" | "card_context_regex";
    reason: string | null;
    source_url?: string | null;
    card_context?: boolean;
  };
  metadata_completeness: {
    has_profile_identity: boolean;
    has_thumbnail: boolean;
    has_title_or_caption: boolean;
    has_posted_text: boolean;
    has_duration: boolean;
    has_view_count: boolean;
    has_detail_metrics: boolean;
  };
  capture_status: WholeProfileHarvestCaptureStatus;
  backend_item: WholeProfileHarvestBackendItem | null;
  extraction_source?: string | null;
  profile_card_evidence?: Record<string, unknown>;
};

export type WholeProfileHarvestTargetStatusSummary = Record<WholeProfileHarvestCaptureStatus, number>;

export type WholeProfileHarvestClassificationStatus = "idle" | "running" | "success" | "failed";

export type WholeProfileHarvestClassificationCounts = WholeProfileHarvestTargetStatusSummary & {
  collect: number;
  skip: number;
};

export type WholeProfileHarvestClassificationTarget = {
  aweme_id: string;
  classification: WholeProfileHarvestCaptureStatus;
  collect: boolean;
  reason: string;
  required_missing_fields: string[];
  existing_item_id: string | null;
  metadata_status: string | null;
  review_status: string | null;
  video_url: string | null;
  source_url: string | null;
  thumbnail_url: string | null;
  caption: string | null;
};

export type WholeProfileHarvestClassificationState = {
  status: WholeProfileHarvestClassificationStatus;
  started_at: string | null;
  completed_at: string | null;
  last_error: string | null;
  profile_url: string | null;
  sec_uid: string | null;
  schema_version: "douyin_profile_video_classification_result.v1" | null;
  collection_mode: string | null;
  database_lookup_status: string | null;
  total_candidates: number;
  counts: WholeProfileHarvestClassificationCounts;
  targets: WholeProfileHarvestClassificationTarget[];
  collect_aweme_ids: string[];
  skip_aweme_ids: string[];
  diagnostics: unknown | null;
};

export type WholeProfileHarvestQueuePreviewItem = {
  index: number;
  aweme_id: string;
  capture_status: WholeProfileHarvestCaptureStatus;
  source_url: string | null;
  title: string | null;
  thumbnail_url: string | null;
};

export type WholeProfileHarvestRejectedCandidate = {
  candidate_id: string;
  reason: string | null;
  source: string | null;
};

export type WholeProfileHarvestDryRunResult = {
  index: number;
  aweme_id: string;
  target_url: string;
  status: "pass" | "fail";
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

export type WholeProfileHarvestQueueItem = {
  index: number;
  aweme_id: string;
  capture_status: WholeProfileHarvestCaptureStatus;
  status: WholeProfileHarvestQueueStatus;
  attempts: number;
  retry_count?: number;
  checkpoint_sequence: number | null;
  extraction_result: "extracted" | "skipped" | "failed" | null;
  last_error: string | null;
  last_attempt_at?: string | null;
  saved_at?: string | null;
  capture_inbox_item_id: string | null;
  backend_item_id?: string | null;
  metadata_status?: string | null;
  source_url: string | null;
  thumbnail_url?: string | null;
  caption?: string | null;
  profile_card_evidence: Record<string, unknown>;
};

export type WholeProfileHarvestMetrics = {
  duration_seconds: number | null;
  duration_text: string | null;
  duration_raw?: number | null;
  duration_validation_result?: string | null;
  duration_candidate_list?: Array<{ source: string; raw_value: number | null; normalized_seconds: number | null; accepted: boolean; reason: string }> | null;
  like_count: number | null;
  comment_count: number | null;
  favorite_count: number | null;
  share_count: number | null;
  current_modal_id_before: string | null;
  current_modal_id_after: string | null;
  extracted_aweme_id: string | null;
  source_used?: string | null;
  caption?: string | null;
  thumbnail_url?: string | null;
  thumbnail_source?: string | null;
  thumbnail_candidates_count?: number | null;
  thumbnail_rejected_ui_chrome_count?: number | null;
  thumbnail_rejection_reasons?: string[] | null;
  posted_text?: string | null;
  posted_text_raw?: string | null;
  posted_at?: string | null;
  posted_display?: string | null;
  posted_source?: string | null;
  posted_parse_confidence?: string | null;
};

export type WholeProfileHarvestTargetStage = "open_modal" | "wait_modal" | "extract_metrics" | "validate_identity" | "build_payload" | "guard_payload" | "flush_backend" | "verify_backend_item";

export type WholeProfileHarvestFailureSummary = {
  failed_count: number;
  top_failure_reasons: { code: string; count: number }[];
  sample_failed_targets: { aweme_id: string; code: string; stage: string | null }[];
};

export type WholeProfileHarvestLastError = {
  code: string;
  message: string;
  failed_count?: number;
  top_failure_reasons?: { code: string; count: number }[];
  sample_failed_aweme_ids?: string[];
  details?: unknown;
};

export type WholeProfileHarvestResult = WholeProfileHarvestMetrics & {
  index: number;
  aweme_id: string;
  status: "extracted" | "skipped" | "failed";
  stage: WholeProfileHarvestTargetStage | null;
  attempts: number;
  checkpoint_sequence: number | null;
  error: string | null;
  error_code: string | null;
  error_message: string | null;
  modal_opened: boolean;
  modal_id_matched: boolean;
  metrics_extracted: boolean;
  payload_built: boolean;
  backend_called: boolean;
  backend_status: number | null;
  backend_error_code: string | null;
  capture_inbox_item_id: string | null;
  target_url: string | null;
  data_integrity_status: "passed" | "failed" | "not_checked";
  profile_card_evidence: Record<string, unknown>;
  started_at: string | null;
  completed_at: string;
};

export type WholeProfileHarvestTraceEntry = {
  at: string;
  action: string;
  phase: string;
  message?: string;
  details?: unknown;
};

export type PostScanCounterSnapshot = {
  status: "applied" | "backend_unavailable" | "fallback";
  source: "backend_capture_inbox_profile_summary" | "local_fallback_backend_unavailable" | "backend_empty_disproves_snapshot";
  profile_identifier: string;
  scanned_total: number;
  backend_captured_aweme_ids?: string[];
  backend_captured: number | null;
  backend_ready: number | null;
  backend_dup: number | null;
  backend_fail: number | null;
  already_collected: number;
  incomplete: number;
  need_retry: number;
  new: number;
  queue: number;
  applied_at: string;
};

export type WholeProfileHarvestState = {
  schema_version: typeof WHOLE_PROFILE_HARVEST_SCHEMA_VERSION;
  run_id: string | null;
  status: WholeProfileHarvestStatus;
  phase: string;
  profile_url: string | null;
  source_url: string | null;
  source_modal_aweme_id: string | null;
  capture_session_id: string | null;
  /** Durable tail-gap UI authority: survives popup reopen without fossil RAM. */
  hybrid_tail_gap_presentation: "none" | "unreachable_offer" | "closed";
  layer: {
    profile_scan_ready: boolean;
    dry_run_ready: boolean;
    harvest_ready: boolean;
  };
  page_context: WholeProfileHarvestPageContext;
  calibration: WholeProfileHarvestCalibration;
  workflow: DouyinScannerWorkflowState;
  scan_job: PersistentScanJobRecord;
  collect_job: PersistentCollectJobRecord;
  active_collect_runtime: ActiveCollectRuntimeRecord;
  profile_scan: {
    status: WholeProfileHarvestVerifyStatus;
    raw_candidate_count: number;
    accepted_target_count: number;
    rejected_target_count: number;
    targets: string[];
    target_details: WholeProfileHarvestTargetDetail[];
    rejected_candidates_sample: WholeProfileHarvestRejectedCandidate[];
    scan_rounds: number;
    stop_reason: string | null;
    scroll_container_found: boolean;
    diagnostics: unknown | null;
  };
  post_scan_counter_snapshot: PostScanCounterSnapshot | null;
  target_status: WholeProfileHarvestTargetStatusSummary;
  classification: WholeProfileHarvestClassificationState;
  verify: {
    status: WholeProfileHarvestVerifyStatus;
    started_at: string | null;
    completed_at: string | null;
    raw_candidate_count: number;
    accepted_target_count: number;
    rejected_target_count: number;
    verified_target_count: number;
    targets: string[];
    target_details: WholeProfileHarvestTargetDetail[];
    rejected_candidates_sample: WholeProfileHarvestRejectedCandidate[];
    scan_rounds: number;
    stop_reason: string | null;
    scroll_container_found: boolean;
    diagnostics: unknown | null;
  };
  dry_run: {
    status: WholeProfileHarvestDryRunStatus;
    mode: WholeProfileHarvestDryRunMode | null;
    sample_size: number;
    sampled_indexes: number[];
    sampled_aweme_ids: string[];
    current_index: number;
    pass: number;
    fail: number;
    results: WholeProfileHarvestDryRunResult[];
    started_at: string | null;
    completed_at: string | null;
  };
  harvest_options: {
    mode: WholeProfileHarvestMode;
    batch: WholeProfileHarvestBatch;
    batch_limit: number | null;
    speed: WholeProfileHarvestSpeed;
    unattended_safe_mode: boolean;
  };
  harvest: {
    status: WholeProfileHarvestRunStatus;
    mode: WholeProfileHarvestMode;
    batch_limit: number | "all";
    speed: WholeProfileHarvestSpeed;
    simulation_mode: "local_checkpoint_only" | "real_modal_extraction_no_backend";
    queue: WholeProfileHarvestQueueItem[];
    queue_preview: WholeProfileHarvestQueuePreviewItem[];
    planned_total: number;
    current_index: number;
    current_aweme_id: string | null;
    updated: number;
    skipped: number;
    failed: number;
    flushed: number;
    pending: number;
    processed: number;
    checkpoint_count: number;
    resume_from_index: number | null;
    started_at: string | null;
    updated_at: string | null;
    paused_reason: string | null;
    pause_message: string | null;
    pause_requested: boolean;
    pause_requested_at: string | null;
    pause_acknowledged_at: string | null;
    pause_reason: string | null;
    resume_available: boolean;
    last_safety_event: string | null;
    last_checkpoint_at: string | null;
    last_success_at: string | null;
    last_backend_response: unknown | null;
    last_payload_summary: unknown | null;
    pause_diagnostics: unknown | null;
    collect_trace: Array<{
      at: string;
      phase: string;
      aweme_id: string | null;
      target_index: number | null;
      queue_size: number;
      processed: number;
      pending: number;
      updated: number;
      skipped: number;
      failed: number;
      note: string;
      details?: unknown;
    }>;
    capture_session_status: "idle" | "ready" | "failed";
    backend: {
      capture_session: {
        status: "idle" | "creating" | "ready" | "failed";
        session_id: string | null;
        created: boolean | null;
        request_summary: unknown | null;
        response_summary: unknown | null;
        error_code: string | null;
        error_message: string | null;
        updated_at: string | null;
      };
      payload_preview: {
        status: "idle" | "ready" | "guard_failed" | "missing_result" | "failed";
        target_aweme_id: string | null;
        removed_fields: { path: string; reason: "not_allowlisted" }[];
        guard: { ok: boolean; code?: string; path?: string; offending_paths: string[] } | null;
        payload: unknown | null;
        summary: unknown | null;
        updated_at: string | null;
      };
      one_item_flush: {
        status: "idle" | "running" | "succeeded" | "failed";
        started_at: string | null;
        completed_at: string | null;
        request_summary: unknown | null;
        response_summary: unknown | null;
        error: {
          code: string | null;
          message: string | null;
          details: unknown | null;
        } | null;
        capture_inbox_item_id: string | null;
        item_created_or_updated: boolean | null;
        verify_status: "idle" | "verified" | "not_found" | "failed";
        verify_response: unknown | null;
      };
      batch_flush: {
        status: "idle" | "running" | "paused" | "completed" | "completed_with_warnings" | "failed";
        mode: WholeProfileHarvestMode;
        queue: WholeProfileHarvestQueueItem[];
        queue_total: number;
        current_index: number;
        current_aweme_id: string | null;
        processed: number;
        succeeded: number;
        skipped: number;
        failed: number;
        pending: number;
        checkpoint_count: number;
        resume_from_index: number | null;
        last_flushed_aweme_id: string | null;
        started_at: string | null;
        updated_at: string | null;
        completed_at: string | null;
        pause_reason: string | null;
        last_error_code: string | null;
        last_error_message: string | null;
        last_verify_status: "idle" | "verified" | "not_found" | "failed";
      };
    };
    stop_requested: boolean;
    results: WholeProfileHarvestResult[];
    failure_summary: WholeProfileHarvestFailureSummary | null;
  };
  safety: {
    safety_status: "safe" | "needs_attention" | "stale" | "blocked" | "recoverable" | "fatal";
    safety_reason: string | null;
    safety_evidence: string | null;
    safety_last_checked_at: string | null;
    safety_recoverable: boolean;
    safety_user_action_required: boolean;
    safety_checkpoint: {
      schema_version: "douyin_safety_checkpoint.v1";
      profile_url: string | null;
      session_id: string | null;
      batch_run_id: string | null;
      item_run_id: string | null;
      target_aweme: string | null;
      current_index: number | null;
      saved_count: number;
      failed_count: number;
      pending_count: number;
      safety_status: "safe" | "needs_attention" | "stale" | "blocked" | "recoverable" | "fatal";
      safety_reason: string | null;
      safety_evidence: string | null;
      next_pending_aweme: string | null;
      created_at: string | null;
    } | null;
    captcha_detected: boolean;
    captcha_reason: "captcha" | "security_check" | "login_required" | "abnormal_traffic" | "access_denied" | null;
    captcha_evidence_text: string | null;
    checkpoint_detected: boolean;
    login_required: boolean;
    abnormal_traffic_detected: boolean;
    consecutive_errors: number;
    max_consecutive_errors: number;
    speed: WholeProfileHarvestSpeed;
    last_delay_ms: number | null;
    last_delay_started_at: string | null;
    last_delay_completed_at: string | null;
    last_pause_at: string | null;
    pause_after_every: number;
    processed_since_last_pause: number;
    scheduled_pause_active: boolean;
    scheduled_pause_started_at: string | null;
    scheduled_pause_until: string | null;
    last_scheduled_pause_ms: number | null;
    tab_health: {
      status: "unknown" | "healthy" | "not_douyin" | "content_script_missing" | "detector_failed";
      last_checked_at: string | null;
      current_url: string | null;
      page_type: "profile" | "modal" | "video" | "unknown" | null;
    };
    resume_check: {
      status: "idle" | "checking" | "ready" | "blocked";
      last_checked_at: string | null;
      blocked_reason: string | null;
    };
  };
  last_error: string | WholeProfileHarvestLastError | null;
  debug: {
    trace: WholeProfileHarvestTraceEntry[];
    last_action: string | null;
    last_action_clicked: string | null;
    last_action_result: string | null;
    last_action_error: string | null;
    last_action_started_at: string | null;
    last_action_finished_at: string | null;
    active_task: DouyinScannerActiveTask;
    busy_source: string | null;
    busy_stale: boolean;
    last_request_summary: unknown | null;
    last_response_summary: unknown | null;
    legacy_state_summary: unknown | null;
    pending_verify_after_navigation?: boolean;
    navigation_method?: string;
    original_modal_url?: string | null;
    last_primary_action_key_clicked?: string | null;
    last_primary_action_label_clicked?: string | null;
    last_primary_action_dispatch_target?: string | null;
  };
  started_at: string | null;
  updated_at: string | null;
};

export function createDouyinScannerWorkflowStep(status: DouyinScannerWorkflowStatus = "idle", at: string | null = null, error: string | null = null): DouyinScannerWorkflowStep {
  return { status, started_at: status === "running" ? at : null, updated_at: at, completed_at: status === "success" || status === "failed" ? at : null, last_error: error };
}

export function createDouyinScannerCollectionStep(status: DouyinScannerCollectionStatus = "idle", at: string | null = null, error: string | null = null): DouyinScannerCollectionStep {
  return { status, started_at: status === "opening_target" || status === "running" || status === "pausing" || status === "paused" ? at : null, updated_at: at, completed_at: status === "success" || status === "failed" ? at : null, last_error: error };
}

export function createDouyinScannerWorkflowState(now: string | null = null): DouyinScannerWorkflowState {
  return { scan: createDouyinScannerWorkflowStep("idle", now), classification: createDouyinScannerWorkflowStep("idle", now), collection: createDouyinScannerCollectionStep("idle", now), active_task: null, action_lock: null };
}

export function createPersistentScanJobRecord(now: string | null = null): PersistentScanJobRecord {
  return {
    scan_job_id: null,
    status: "idle",
    profile_identifier: null,
    cursor: null,
    has_more_state: null,
    page_count: 0,
    request_count: 0,
    last_http_status: null,
    last_status_code: null,
    last_error: null,
    started_at: null,
    updated_at: now,
    completed_at: null,
    next_retry_at: null,
    retry_count: 0,
    resume_source: null,
    continuation_cursor_source: null,
    continuation_resume_strategy: null,
    continuation_resume_result: null,
    continuation_replay_duplicate_pages_detected: null,
    continuation_replay_duplicate_count: null,
    continuation_recovery_attempted: null,
    continuation_recovery_result: null,
    continuation_checkpoint_id: null,
    continuation_run_id: null,
    continuation_persisted_total: null,
    continuation_progress_total: null,
    current_run_new_inserted_total: null,
    current_run_duplicate_existing_total: null,
    consecutive_no_new_pages: 0,
    total_discovered: 0,
    total_persisted: 0,
    expected_count: null,
    remaining_estimate: null
  };
}

export function createPersistentCollectJobRecord(now: string | null = null): PersistentCollectJobRecord {
  return {
    job_id: null,
    profile_identifier: null,
    normalized_profile_identifier: null,
    state: "idle",
    started_at: null,
    updated_at: now,
    heartbeat_at: null,
    completed_at: null,
    runner_ack_at: null,
    startup_deadline_at: null,
    startup_timeout_ms: null,
    failure_reason: null,
    last_error: null,
    current_step: null,
    current_aweme_id: null,
    current_item_index: null,
    batch_limit: null,
    job_type: null,
    selected_count: 0,
    selected_aweme_ids: [],
    selected_indexes: [],
    start_index: null,
    runtime_generation: 0,
    attempted_count: 0,
    succeeded_count: 0,
    failed_count: 0,
    skipped_count: 0,
    pre_batch_backend_captured: null,
    pre_batch_backend_ready: null,
    pre_batch_backend_dup: null,
    pre_batch_backend_fail: null,
    pre_batch_new: null,
    pre_batch_queue: null,
    post_batch_backend_captured: null,
    post_batch_backend_ready: null,
    post_batch_backend_dup: null,
    post_batch_backend_fail: null,
    post_batch_new: null,
    post_batch_queue: null,
    batch_delta_captured: null,
    batch_delta_queue: null,
    lock_owner: null,
    lock_acquired_at: null,
    lock_expires_at: null,
    recoverable: false,
    stale_reason: null,
    heartbeat_updates_count: 0,
    lock_released: true
  };
}

export function createActiveCollectRuntimeRecord(now: string | null = null): ActiveCollectRuntimeRecord {
  return {
    job_id: null,
    runtime_version: "phase_3r_4a_single_runtime_authority.v1",
    runtime_generation: 0,
    render_generation: 0,
    canonical_state: "idle",
    canonical_phase: "idle",
    current_step: null,
    current_aweme_id: null,
    current_item_index: null,
    batch_limit: null,
    selected_count: 0,
    attempted_count: 0,
    succeeded_count: 0,
    failed_count: 0,
    skipped_count: 0,
    pre_batch_backend_captured: null,
    pre_batch_backend_ready: null,
    pre_batch_backend_dup: null,
    pre_batch_backend_fail: null,
    pre_batch_new: null,
    pre_batch_queue: null,
    latest_progress_captured: null,
    latest_progress_queue: null,
    latest_progress_new: null,
    heartbeat_at: null,
    lock_owner: null,
    lock_expires_at: null,
    last_update_source: null,
    last_update_writer: null,
    writer_epoch_ms: null,
    writer_conflict_rejected: false,
    stale_write_rejected: false,
    rejected_update_source: null,
    rejected_update_generation: null,
    trace: {
      active_runner_trace: null,
      popup_render_trace: null,
      stale_check_trace: null,
      recovery_trace: null,
      queue_filtering: null,
      per_item_backend_writes: null,
      timing: null,
      summary: null
    },
    updated_at: now
  };
}

export function createWholeProfileHarvestIdleState(now: string | null = null): WholeProfileHarvestState {
  return {
    schema_version: WHOLE_PROFILE_HARVEST_SCHEMA_VERSION,
    run_id: null,
    status: "idle",
    phase: "idle",
    profile_url: null,
    source_url: null,
    source_modal_aweme_id: null,
    capture_session_id: null,
    hybrid_tail_gap_presentation: "none",
    layer: { profile_scan_ready: false, dry_run_ready: false, harvest_ready: false },
    page_context: { page_type: null, current_url: null, modal_id: null, content_script_status: null, detector_status: null, modal_transition: null },
    calibration: createWholeProfileHarvestCalibration(null),
    workflow: createDouyinScannerWorkflowState(now),
    scan_job: createPersistentScanJobRecord(now),
    collect_job: createPersistentCollectJobRecord(now),
    active_collect_runtime: createActiveCollectRuntimeRecord(now),
    profile_scan: {
      status: "idle",
      raw_candidate_count: 0,
      accepted_target_count: 0,
      rejected_target_count: 0,
      targets: [],
      target_details: [],
      rejected_candidates_sample: [],
      scan_rounds: 0,
      stop_reason: null,
      scroll_container_found: false,
      diagnostics: null
    },
    post_scan_counter_snapshot: null,
    target_status: emptyTargetStatusSummary(),
    classification: emptyClassificationState(),
    verify: {
      status: "idle",
      started_at: null,
      completed_at: null,
      raw_candidate_count: 0,
      accepted_target_count: 0,
      rejected_target_count: 0,
      verified_target_count: 0,
      targets: [],
      target_details: [],
      rejected_candidates_sample: [],
      scan_rounds: 0,
      stop_reason: null,
      scroll_container_found: false,
      diagnostics: null
    },
    dry_run: {
      status: "idle",
      mode: null,
      sample_size: 0,
      sampled_indexes: [],
      sampled_aweme_ids: [],
      current_index: 0,
      pass: 0,
      fail: 0,
      results: [],
      started_at: null,
      completed_at: null
    },
    harvest_options: { mode: "new_and_incomplete", batch: "next_10", batch_limit: 10, speed: "safe", unattended_safe_mode: false },
    harvest: {
      status: "idle",
      mode: "new_and_incomplete",
      batch_limit: 10,
      speed: "safe",
      simulation_mode: "real_modal_extraction_no_backend",
      queue: [],
      queue_preview: [],
      planned_total: 0,
      current_index: 0,
      current_aweme_id: null,
      updated: 0,
      skipped: 0,
      failed: 0,
      flushed: 0,
      pending: 0,
      processed: 0,
      checkpoint_count: 0,
      resume_from_index: null,
      started_at: null,
      updated_at: null,
      paused_reason: null,
      pause_message: null,
      pause_requested: false,
      pause_requested_at: null,
      pause_acknowledged_at: null,
      pause_reason: null,
      resume_available: true,
      last_safety_event: null,
      last_checkpoint_at: null,
      last_success_at: null,
      last_backend_response: null,
      last_payload_summary: null,
      pause_diagnostics: null,
      collect_trace: [],
      capture_session_status: "idle",
      backend: {
        capture_session: {
          status: "idle",
          session_id: null,
          created: null,
          request_summary: null,
          response_summary: null,
          error_code: null,
          error_message: null,
          updated_at: null
        },
        payload_preview: {
          status: "idle",
          target_aweme_id: null,
          removed_fields: [],
          guard: null,
          payload: null,
          summary: null,
          updated_at: null
        },
        one_item_flush: {
          status: "idle",
          started_at: null,
          completed_at: null,
          request_summary: null,
          response_summary: null,
          error: null,
          capture_inbox_item_id: null,
          item_created_or_updated: null,
          verify_status: "idle",
          verify_response: null
        },
        batch_flush: {
          status: "idle",
          mode: "new_and_incomplete",
          queue: [],
          queue_total: 0,
          current_index: 0,
          current_aweme_id: null,
          processed: 0,
          succeeded: 0,
          skipped: 0,
          failed: 0,
          pending: 0,
          checkpoint_count: 0,
          resume_from_index: null,
          last_flushed_aweme_id: null,
          started_at: null,
          updated_at: null,
          completed_at: null,
          pause_reason: null,
          last_error_code: null,
          last_error_message: null,
          last_verify_status: "idle"
        }
      },
      stop_requested: false,
      results: [],
      failure_summary: null
    },
    safety: {
      safety_status: "safe",
      safety_reason: null,
      safety_evidence: null,
      safety_last_checked_at: now,
      safety_recoverable: true,
      safety_user_action_required: false,
      safety_checkpoint: null,
      captcha_detected: false,
      captcha_reason: null,
      captcha_evidence_text: null,
      checkpoint_detected: false,
      login_required: false,
      abnormal_traffic_detected: false,
      consecutive_errors: 0,
      max_consecutive_errors: 3,
      speed: "safe",
      last_delay_ms: null,
      last_delay_started_at: null,
      last_delay_completed_at: null,
      last_pause_at: null,
      pause_after_every: 10,
      processed_since_last_pause: 0,
      scheduled_pause_active: false,
      scheduled_pause_started_at: null,
      scheduled_pause_until: null,
      last_scheduled_pause_ms: null,
      tab_health: {
        status: "unknown",
        last_checked_at: null,
        current_url: null,
        page_type: null
      },
      resume_check: {
        status: "idle",
        last_checked_at: null,
        blocked_reason: null
      }
    },
    last_error: null,
    debug: {
      trace: [],
      last_action: null,
      last_action_clicked: null,
      last_action_result: null,
      last_action_error: null,
      last_action_started_at: null,
      last_action_finished_at: null,
      active_task: null,
      busy_source: null,
      busy_stale: false,
      last_request_summary: null,
      last_response_summary: null,
      legacy_state_summary: null
    },
    started_at: null,
    updated_at: now
  };
}

export function emptyTargetStatusSummary(): WholeProfileHarvestTargetStatusSummary {
  return { new: 0, incomplete: 0, complete: 0, failed: 0, skipped: 0, unknown: 0 };
}

export function emptyClassificationCounts(): WholeProfileHarvestClassificationCounts {
  return { ...emptyTargetStatusSummary(), collect: 0, skip: 0 };
}

export function emptyClassificationState(): WholeProfileHarvestClassificationState {
  return {
    status: "idle",
    started_at: null,
    completed_at: null,
    last_error: null,
    profile_url: null,
    sec_uid: null,
    schema_version: null,
    collection_mode: null,
    database_lookup_status: null,
    total_candidates: 0,
    counts: emptyClassificationCounts(),
    targets: [],
    collect_aweme_ids: [],
    skip_aweme_ids: [],
    diagnostics: null
  };
}

export function computeTargetStatusSummary(targetDetails: WholeProfileHarvestTargetDetail[]): WholeProfileHarvestTargetStatusSummary {
  const summary = emptyTargetStatusSummary();
  for (const target of targetDetails) summary[target.capture_status ?? "unknown"] += 1;
  return summary;
}

export function targetStatusIncludedInHarvestMode(status: WholeProfileHarvestCaptureStatus, mode: WholeProfileHarvestMode): boolean {
  if (mode === "refresh_all") return status !== "skipped";
  if (mode === "new_only") return status === "new" || status === "unknown";
  return status === "new" || status === "incomplete" || status === "failed" || status === "unknown";
}

export function buildHarvestQueuePreview(state: WholeProfileHarvestState): WholeProfileHarvestQueuePreviewItem[] {
  const targets = applyLocalHarvestResultOverrides(state.profile_scan.target_details, state.harvest.results, state.harvest_options.mode)
    .filter((target) => targetStatusIncludedInHarvestMode(target.capture_status, state.harvest_options.mode));
  const limited = typeof state.harvest_options.batch_limit === "number" ? targets.slice(0, state.harvest_options.batch_limit) : targets;
  return limited.map((target) => ({ index: target.index, aweme_id: target.aweme_id, capture_status: target.capture_status, source_url: target.source_url, title: target.title, thumbnail_url: target.thumbnail_url }));
}

export function applyLocalHarvestResultOverrides(targetDetails: WholeProfileHarvestTargetDetail[], results: WholeProfileHarvestResult[], mode: WholeProfileHarvestMode): WholeProfileHarvestTargetDetail[] {
  if (mode === "refresh_all" || results.length === 0) return targetDetails;
  const resultByAwemeId = new Map(results.map((result) => [result.aweme_id, result]));
  return targetDetails.map((target) => {
    const result = resultByAwemeId.get(target.aweme_id);
    if (!result) return target;
    if (result.status === "extracted") return { ...target, capture_status: "complete" };
    if (result.status === "failed") return { ...target, capture_status: "failed" };
    if (result.status === "skipped") return { ...target, capture_status: "skipped" };
    return target;
  });
}

export function createWholeProfileHarvestCalibration(value: unknown): WholeProfileHarvestCalibration {
  const normalized = normalizeDouyinCalibration(value);
  const legacy = value && typeof value === "object" ? value as { source_key?: unknown; viewport_warning?: unknown; status?: unknown; point_count?: unknown; ready?: unknown } : null;
  const legacyPointCount = typeof legacy?.point_count === "number" ? legacy.point_count : normalized.point_count;
  const legacyReady = legacy?.ready === true || (legacy?.status === "calibrated" && legacyPointCount >= REQUIRED_DOUYIN_CALIBRATION_POINTS.length);
  return {
    ...normalized,
    status: legacyReady ? "calibrated" : normalized.status === "needed" ? "missing" : normalized.status,
    ready: legacyReady ? true : normalized.ready,
    point_count: Math.max(normalized.point_count, legacyPointCount),
    source_key: typeof legacy?.source_key === "string" ? legacy.source_key : normalized.source,
    viewport_warning: typeof legacy?.viewport_warning === "string" ? legacy.viewport_warning : null
  } satisfies WholeProfileHarvestCalibration;
}

export function calibrationFingerprint(calibration: WholeProfileHarvestCalibration | null | undefined): string {
  if (!calibration || typeof calibration !== "object") return "null";
  const normalized = createWholeProfileHarvestCalibration(calibration);
  return JSON.stringify({
    status: normalized.status,
    ready: normalized.ready,
    layout: normalized.layout,
    source_url: normalized.source_url,
    profile_url: normalized.profile_url,
    aweme_id: normalized.aweme_id,
    source_key: normalized.source_key,
    viewport_warning: normalized.viewport_warning,
    point_count: normalized.point_count,
    points: REQUIRED_DOUYIN_CALIBRATION_POINTS.reduce<Record<string, unknown>>((acc, key) => {
      const points = normalized.points ?? {};
      acc[key] = points[key] ?? null;
      return acc;
    }, {})
  });
}

export function chooseMoreCompleteCalibration(
  primary: WholeProfileHarvestCalibration | null | undefined,
  fallback: WholeProfileHarvestCalibration | null | undefined
): WholeProfileHarvestCalibration {
  const primaryNormalized = createWholeProfileHarvestCalibration(primary);
  const fallbackNormalized = createWholeProfileHarvestCalibration(fallback);
  const primaryReady = primaryNormalized.ready === true && primaryNormalized.status === "calibrated";
  const fallbackReady = fallbackNormalized.ready === true && fallbackNormalized.status === "calibrated";
  if (primaryReady && !fallbackReady) return primaryNormalized;
  if (fallbackReady && !primaryReady) return fallbackNormalized;
  if (fallbackNormalized.point_count > primaryNormalized.point_count) return fallbackNormalized;
  return primaryNormalized;
}

export type ScannerStateValidationResult = {
  state: WholeProfileHarvestState;
  diagnostics: Record<string, unknown>;
};

function lastErrorCode(value: WholeProfileHarvestState["last_error"]): string | null {
  if (typeof value === "string") return value.split(":", 1)[0] || null;
  if (value && typeof value === "object") return value.code;
  return null;
}

export function validateScannerState(state: WholeProfileHarvestState, at = new Date().toISOString()): ScannerStateValidationResult {
  const violations: string[] = [];
  let next = state;
  const scanRounds = Math.max(next.verify.scan_rounds, next.profile_scan.scan_rounds);
  if (scanRounds <= 0 && lastErrorCode(next.last_error) === "profile_scan_incomplete") {
    violations.push("scanRounds=0_profile_scan_incomplete");
    const diagnostics = {
      ...(next.debug.last_response_summary && typeof next.debug.last_response_summary === "object" ? next.debug.last_response_summary as Record<string, unknown> : {}),
      state_machine_version: "22C-9C",
      state_validator_repaired: "yes",
      state_validator_repair_reason: "profile_scan_incomplete_requires_started_scan_round",
      original_scan_error_before_normalization: "profile_scan_incomplete",
      normalized_scan_error: "profile_scan_no_round_started",
      scan_error_normalizer_applied: "yes",
      no_round_guard_applied: "yes",
      scan_rounds: scanRounds,
      validated_at: at
    };
    next = {
      ...next,
      last_error: "profile_scan_no_round_started: Profile scan stopped before a scan round started.",
      debug: { ...next.debug, last_action_error: "profile_scan_no_round_started", last_response_summary: diagnostics },
      updated_at: at
    };
  }
  const lastSummary = next.debug.last_response_summary && typeof next.debug.last_response_summary === "object"
    ? next.debug.last_response_summary as Record<string, unknown>
    : {};
  const activeScanProfileEngine = String(lastSummary.active_scan_profile_engine ?? "");
  const isMinimalScanProfile22C11B = activeScanProfileEngine === "minimal_active_works_scan_profile_22C11B"
    || activeScanProfileEngine === "live_network_stream_profile_collector_22C12F"
    || activeScanProfileEngine === "network_first_profile_post_collector_22C12B"
    || lastSummary.scan_action_trace_version === "22C-11B"
    || lastSummary.scan_action_trace_version === "22C-12B"
    || lastSummary.scanner_runtime_version === "22C-11B"
    || lastSummary.scanner_runtime_version === "22C-12B";
  const productiveProbeWithoutDirectScan = scanRounds <= 0
    && !isMinimalScanProfile22C11B
    && lastErrorCode(next.last_error) === "profile_scan_no_round_started"
    && lastSummary.profile_dom_probe_status === "completed"
    && lastSummary.profile_grid_ready === true
    && Number(lastSummary.aweme_id_count ?? 0) > 0
    && lastSummary.direct_legacy_scan_attempted !== "yes";
  if (productiveProbeWithoutDirectScan) {
    violations.push("productive_probe_without_direct_legacy_scan");
    const diagnostics = {
      ...lastSummary,
      normalized_scan_error: "direct_legacy_scan_handler_missing",
      scan_finalization_result: "failed",
      scan_failure_stage: "direct_legacy_scanner",
      scan_no_round_reason: "direct_legacy_scan_not_attempted_after_productive_probe",
      direct_legacy_scan_required_repaired_at: at,
      validated_at: at
    };
    next = {
      ...next,
      last_error: "direct_legacy_scan_handler_missing: Productive DOM probe completed, but direct legacy scanner was not attempted.",
      debug: {
        ...next.debug,
        last_action_error: "direct_legacy_scan_handler_missing",
        last_response_summary: diagnostics
      },
      verify: {
        ...next.verify,
        diagnostics: {
          ...(next.verify.diagnostics && typeof next.verify.diagnostics === "object" ? next.verify.diagnostics as Record<string, unknown> : {}),
          ...diagnostics
        }
      },
      profile_scan: {
        ...next.profile_scan,
        diagnostics: {
          ...(next.profile_scan.diagnostics && typeof next.profile_scan.diagnostics === "object" ? next.profile_scan.diagnostics as Record<string, unknown> : {}),
          ...diagnostics
        }
      },
      updated_at: at
    };
  }
  const noRoundWithoutProbe = scanRounds <= 0
    && !isMinimalScanProfile22C11B
    && lastErrorCode(next.last_error) === "profile_scan_no_round_started"
    && !((next.debug.last_response_summary as Record<string, unknown> | null | undefined)?.scan_action_trace_version
      || ((next.verify.diagnostics as Record<string, unknown> | null | undefined)?.scan_action_trace_version)
      || ((next.profile_scan.diagnostics as Record<string, unknown> | null | undefined)?.scan_action_trace_version));
  if (noRoundWithoutProbe) {
    violations.push("profile_scan_no_round_started_without_canonical_probe_trace");
    const diagnostics = {
      state_machine_version: "22C-9C",
      state_validator_version: "22C-9C",
      normalized_scan_error: "scan_profile_legacy_route_bypassed_probe",
      scan_action_trace_version: "missing",
      legacy_scan_profile_route_invoked: "yes",
      legacy_scan_profile_delegated_to_canonical: "no",
      scan_no_round_reason: "legacy_route_bypassed_probe",
      repaired_at: at
    };
    next = {
      ...next,
      last_error: "scan_profile_legacy_route_bypassed_probe: A legacy Scan Profile route bypassed the DOM probe.",
      debug: { ...next.debug, last_action_error: "scan_profile_legacy_route_bypassed_probe", last_response_summary: diagnostics },
      verify: { ...next.verify, diagnostics: { ...(next.verify.diagnostics && typeof next.verify.diagnostics === "object" ? next.verify.diagnostics as Record<string, unknown> : {}), ...diagnostics } },
      profile_scan: { ...next.profile_scan, diagnostics: { ...(next.profile_scan.diagnostics && typeof next.profile_scan.diagnostics === "object" ? next.profile_scan.diagnostics as Record<string, unknown> : {}), ...diagnostics } }
    };
  }
  return { state: next, diagnostics: { state_machine_version: "22C-9C", state_validator_version: "22C-9C", violations, repaired: violations.length > 0 ? "yes" : "no", validated_at: at } };
}

export function normalizeWholeProfileHarvestState(value: unknown, now: string | null = null): WholeProfileHarvestState {
  if (!value || typeof value !== "object" || (value as { schema_version?: unknown }).schema_version !== WHOLE_PROFILE_HARVEST_SCHEMA_VERSION) {
    return createWholeProfileHarvestIdleState(now);
  }
  const idle = createWholeProfileHarvestIdleState(now);
  const incoming = value as WholeProfileHarvestState;
  const normalizedProfileDetails = (incoming.profile_scan?.target_details ?? []).map(normalizeTargetDetailShape);
  const normalizedVerifyDetails = (incoming.verify?.target_details ?? []).map(normalizeTargetDetailShape);
  const normalized = {
    ...idle,
    ...incoming,
    hybrid_tail_gap_presentation: incoming.hybrid_tail_gap_presentation ?? "none",
    calibration: createWholeProfileHarvestCalibration(incoming.calibration),
    workflow: { ...idle.workflow, ...(incoming.workflow ?? {}), scan: { ...idle.workflow.scan, ...(incoming.workflow?.scan ?? {}) }, classification: { ...idle.workflow.classification, ...(incoming.workflow?.classification ?? {}) }, collection: { ...idle.workflow.collection, ...(incoming.workflow?.collection ?? {}) } },
    scan_job: { ...idle.scan_job, ...((incoming as { scan_job?: Partial<PersistentScanJobRecord> }).scan_job ?? {}) },
    collect_job: { ...idle.collect_job, ...((incoming as { collect_job?: Partial<PersistentCollectJobRecord> }).collect_job ?? {}) },
    active_collect_runtime: {
      ...idle.active_collect_runtime,
      ...((incoming as { active_collect_runtime?: Partial<ActiveCollectRuntimeRecord> }).active_collect_runtime ?? {}),
      trace: {
        ...idle.active_collect_runtime.trace,
        ...((incoming as { active_collect_runtime?: { trace?: Partial<ActiveCollectRuntimeTraceBlock> } }).active_collect_runtime?.trace ?? {})
      }
    },
    profile_scan: { ...idle.profile_scan, ...(incoming.profile_scan ?? {}), target_details: normalizedProfileDetails },
    post_scan_counter_snapshot: incoming.post_scan_counter_snapshot ?? null,
    verify: { ...idle.verify, ...(incoming.verify ?? {}), target_details: normalizedVerifyDetails },
    target_status: incoming.target_status ?? computeTargetStatusSummary(normalizedProfileDetails),
    classification: {
      ...idle.classification,
      ...(incoming.classification ?? {}),
      counts: { ...idle.classification.counts, ...(incoming.classification?.counts ?? {}) },
      targets: incoming.classification?.targets ?? [],
      collect_aweme_ids: incoming.classification?.collect_aweme_ids ?? [],
      skip_aweme_ids: incoming.classification?.skip_aweme_ids ?? []
    },
    harvest: {
      ...idle.harvest,
      ...(incoming.harvest ?? {}),
      backend: {
        ...idle.harvest.backend,
        ...(incoming.harvest?.backend ?? {}),
        capture_session: {
          ...idle.harvest.backend.capture_session,
          ...(incoming.harvest?.backend?.capture_session ?? {})
        },
        payload_preview: {
          ...idle.harvest.backend.payload_preview,
          ...(incoming.harvest?.backend?.payload_preview ?? {})
        },
        one_item_flush: {
          ...idle.harvest.backend.one_item_flush,
          ...(incoming.harvest?.backend?.one_item_flush ?? {})
        },
        batch_flush: {
          ...idle.harvest.backend.batch_flush,
          ...(incoming.harvest?.backend?.batch_flush ?? {})
        }
      }
    },
    safety: {
      ...idle.safety,
      ...(incoming.safety ?? {}),
      tab_health: { ...idle.safety.tab_health, ...(incoming.safety?.tab_health ?? {}) },
      resume_check: { ...idle.safety.resume_check, ...(incoming.safety?.resume_check ?? {}) }
    },
    debug: { ...idle.debug, ...(incoming.debug ?? {}) }
  };
  const validation = validateScannerState(normalized, now ?? new Date().toISOString());
  return {
    ...validation.state,
    debug: {
      ...validation.state.debug,
      legacy_state_summary: {
        ...(validation.state.debug.legacy_state_summary && typeof validation.state.debug.legacy_state_summary === "object" ? validation.state.debug.legacy_state_summary as Record<string, unknown> : {}),
        storage_state_audit: {
          state_machine_version: "22C-9",
          canonical_state_wins: "yes",
          legacy_state_quarantined: "yes",
          validation: validation.diagnostics
        }
      }
    }
  };
}

function normalizeTargetDetailShape(target: WholeProfileHarvestTargetDetail): WholeProfileHarvestTargetDetail {
  return {
    ...target,
    profile_url: target.profile_url ?? null,
    posted_at: target.posted_at ?? null,
    duration_seconds: typeof target.duration_seconds === "number" ? target.duration_seconds : null,
    metadata_completeness: {
      has_profile_identity: Boolean(target.metadata_completeness?.has_profile_identity),
      has_thumbnail: Boolean(target.metadata_completeness?.has_thumbnail),
      has_title_or_caption: Boolean(target.metadata_completeness?.has_title_or_caption),
      has_posted_text: Boolean(target.metadata_completeness?.has_posted_text ?? target.posted_text),
      has_duration: Boolean(target.metadata_completeness?.has_duration ?? target.duration_text ?? target.duration_seconds),
      has_view_count: Boolean(target.metadata_completeness?.has_view_count ?? target.view_count),
      has_detail_metrics: Boolean(target.metadata_completeness?.has_detail_metrics)
    },
    backend_item: target.backend_item ?? null
  };
}

export function appendWholeProfileTrace(state: WholeProfileHarvestState, action: string, message?: string, details?: unknown, now = new Date().toISOString()): WholeProfileHarvestState {
  const entry: WholeProfileHarvestTraceEntry = { at: now, action, phase: state.phase };
  if (typeof message === "string") entry.message = message;
  if (typeof details !== "undefined") entry.details = details;
  return {
    ...state,
    debug: {
      ...state.debug,
      last_action: action,
      trace: [...state.debug.trace, entry].slice(-100)
    },
    updated_at: now
  };
}

