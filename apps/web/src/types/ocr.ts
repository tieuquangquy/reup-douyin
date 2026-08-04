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
    | "WAITING_OCR_REVIEW"
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
};
