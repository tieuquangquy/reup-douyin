export type QualityHandoffSummary = {
  source_video_id: string;
  workflow_version: "QUALITY_LOCALIZATION_V24_1" | string;
  artifact_run_id: string | null;
  final_approval_status: string;
  metadata_status: string;
  rights_status: string;
  manual_export_status: string;
  handoff_status: string;
  next_gate: string | null;
  publish_authorization_status: string | null;
  external_publish_triggered: boolean;
  publish_draft: {
    target_platform?: string | null;
    title?: string;
    caption?: string;
    cta_text?: string;
    hashtags?: Array<{ tag?: string } | string>;
  } | null;
  archive_path: string | null;
  archive_sha256: string | null;
  archive_size_bytes: number | null;
  export_package_id: string | null;
  publish_handoff_id: string | null;
};

export type QualityMetadataApprovalPayload = {
  operator_id?: string;
  target_platform?: "FACEBOOK_REELS";
  title: string;
  caption: string;
  cta_text: string;
  hashtags: string[];
};

export type QualityRightsApprovalPayload = {
  operator_id?: string;
  source_video_reuse_authorized: boolean;
  retained_music_use_authorized: boolean;
  operator_accepts_responsibility: boolean;
};
