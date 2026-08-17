export type HardSubEvent = {
  start_ms: number;
  end_ms: number;
  x: number;
  y: number;
  width: number;
  height: number;
  sample_count: number;
  avg_confidence: number;
  texts?: string[];
  unstable?: boolean;
};

export type OcrCreateResponse = {
  job_id: string;
  status: string;
  source_video_id: string;
  runtime_version: string;
};

export type OcrSummaryResponse = {
  source_video_id: string;
  pipeline_version: string | null;
  provider: string | null;
  text_object_count: number;
  frame_detection_count: number;
  hardsub_events: HardSubEvent[];
  warnings: string[];
  cleaned_video_asset_id: string | null;
  ocr_events_asset_id: string | null;
  visual_approved: boolean;
  clean_produced?: boolean;
  workflow_version?: string | null;
  workflow_stage?:
    | "NOT_STARTED"
    | "PHASE2_READY"
    | "PHASE2_BLOCKED"
    | "WAITING_OCR_REVIEW"
    | "WAITING_DIALOGUE_TRANSLATION_APPROVAL"
    | "PHASE3_PREPARING"
    | "WAITING_TRANSLATION_REVIEW"
    | "READY_FOR_VISUAL_PREVIEW"
    | "WAITING_RESIDUAL_TRIAGE"
    | "WAITING_RESIDUAL_REVIEW"
    | "WAITING_VISUAL_REVIEW"
    | "VISUAL_APPROVED"
    | "WAITING_AUDIO_REVIEW"
    | "AUDIO_APPROVED"
    | "FINAL_READY"
    | string;
  artifact_run_id?: string | null;
  phase1_tracks?: number;
  phase2_model_version?: string | null;
  phase2_content_object_count?: number;
  phase2_handoff_status?: string;
  phase2_blocked_reasons?: string[];
  dialogue_translation_blocked_count?: number;
  requires_dialogue_translation_approval?: boolean;
  local_recovery_summary?: {
    policy_version?: string;
    attempted_tracks?: number;
    recovered_tracks?: number;
    promoted_source_ui_tracks?: number;
    editor_candidates_recovered?: number;
    unresolved_tracks?: number;
    prepared_inputs?: number;
    decoded_frames?: number;
    geometry_tracks_derived?: number;
    geometry_tracks_fail_closed?: number;
  };
  provenance_counts?: Record<string, number>;
  protected_source_tracks?: number;
  provenance_artifact_path?: string | null;
  review_required?: number;
  translation_review_required?: number;
  review_objects?: Array<{
    content_id: string;
    ocr_text_candidate: string;
    roles?: string[];
    review_input_sha256?: string;
    start_frame?: number | null;
    end_frame?: number | null;
    image_path?: string | null;
    provenance_classifications?: string[];
    visual_provenance?: {
      classification?: "EDITOR_OVERLAY" | "SOURCE_INTRINSIC" | "UNCERTAIN" | string;
      confidence?: number;
      policy_version?: string;
      reasons?: string[];
    };
  }>;
  translation_objects?: Array<{
    content_id: string;
    zh_approved: string;
    vi_text_candidate: string;
    roles?: string[];
    quality_flags?: string[];
    review_input_sha256?: string;
  }>;
  visual_preview_asset_id?: string | null;
  visual_preview_status?:
    | "NOT_STARTED"
    | "READY_TO_BUILD"
    | "QUEUED"
    | "RUNNING"
    | "RETRYABLE"
    | "FAILED"
    | "BLOCKED_REVIEW"
    | "READY"
    | string;
  visual_preview_error_code?: string | null;
  visual_preview_error_message?: string | null;
  visual_preview_retryable?: boolean;
  can_render_final?: boolean;
  audio_review_status?: string;
  audio_mix_review_status?: string;
  audio_mix_preview_path?: string | null;
  audio_warnings?: string[];
  timing_fit_summary?: Record<string, number>;
  residual_review_objects?: Array<{
    content_id: string;
    frame_index?: number;
    text?: string;
    confidence?: number;
    geometry?: { x?: number; y?: number; width?: number; height?: number };
    image_path?: string | null;
    ocr_text_corrected_suggested?: string;
    vi_text_suggested?: string;
  }>;
  residual_proposal_objects?: Array<{
    remediation_id?: string;
    proposed_action?: string;
    target_content_id?: string | null;
    ocr_text_suggested?: string;
    render_text_suggested?: string | null;
    proposed_geometry_override?: Record<string, unknown> | null;
    proposed_occurrence?: Record<string, unknown> | null;
    evidence?: Record<string, unknown>;
  }>;
  residual_proposal_sha256?: string | null;
  residual_authority_sha256?: string | null;
  residual_translation_status?: "NOT_REQUIRED" | "NOT_STARTED" | "STALE" | "PARTIAL" | "READY" | string;
  residual_translation_input_sha256?: string | null;
  residual_translation_suggestion_count?: number;
  residual_normalization?: {
    version?: string;
    raw_detection_count?: number;
    temporal_content_count?: number;
    review_content_count?: number;
    protected_source_content_count?: number;
    deduplicated_frame_rows?: number;
  };
  analysis_engine?: string | null;
  analysis_recipe_release?: string | null;
  analysis_recipe_sha256?: string | null;
  pipeline_recipe_release?: string | null;
  pipeline_recipe_sha256?: string | null;
  analysis_metrics?: Record<string, unknown>;
  analysis_mode?: "AUDIO_GUIDED_VISUAL" | "VISUAL_ONLY" | string | null;
  audio_window_count?: number;
  visual_trigger_count?: number;
  all_frame_proxy_size?: [number, number] | null;
  candidate_window_count?: number;
  detector_frame_count?: number;
  analysis_elapsed_s?: number | null;
  analysis_fallback_used?: boolean;
};
