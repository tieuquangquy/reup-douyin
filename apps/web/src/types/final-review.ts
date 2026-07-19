export type RenderOutputStatus = "PLANNED" | "RENDERING" | "READY_FOR_REVIEW" | "APPROVED" | "FAILED" | "ARCHIVED";

export type RenderOutput = {
  id: string;
  workspace_id: string;
  source_video_id: string;
  media_asset_id: string | null;
  status: RenderOutputStatus;
  target_platform: string | null;
  version: number;
  render_type: string | null;
  output_format: string | null;
  width: number | null;
  height: number | null;
  fps: number | null;
  duration_seconds: number | null;
  video_codec: string | null;
  audio_codec: string | null;
  subtitle_burned: boolean;
  audio_strategy: string | null;
  render_version: string | null;
  created_by_job_id: string | null;
  size_bytes: number | null;
  warning_summary_json: Record<string, unknown> | null;
  render_settings_json: Record<string, unknown> | null;
  metadata_json: Record<string, unknown> | null;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
};

export type RenderCreateResponse = {
  job_id: string;
  status: string;
  source_video_id: string;
};

export type MediaAssetManifestEntry = {
  id: string;
  asset_type: string;
  status: string;
  version: number;
  storage_key: string;
  logical_key?: string | null;
  relative_path?: string | null;
  manifest_group?: string | null;
  is_current?: boolean;
  mime_type?: string | null;
  size_bytes?: number | null;
  checksum_sha256?: string | null;
  created_by_job_id?: string | null;
  source_url?: string | null;
  metadata_json?: Record<string, unknown> | null;
};

export type SourceVideoAssetManifest = {
  source_video?: {
    id: string;
    external_id?: string | null;
    source_video_external_id?: string | null;
    source_url?: string | null;
    caption?: string | null;
    duration_seconds?: number | null;
  };
  source_profile?: {
    display_name?: string | null;
    handle?: string | null;
    source_profile_external_id?: string | null;
  };
  assets?: MediaAssetManifestEntry[];
  [key: string]: unknown;
};

export type CompareMode = "side_by_side" | "final_only" | "original_only";

export type FinalReviewChecklistKey =
  | "narration_clear"
  | "subtitle_ok"
  | "timing_ok"
  | "render_clean"
  | "playable"
  | "warnings_checked";

export type ChecklistState = Record<FinalReviewChecklistKey, boolean>;
