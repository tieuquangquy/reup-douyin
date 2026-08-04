import type { Job } from "./jobs";

export type AffiliateCommentPlacementStatus = "DRAFT" | "QUEUED" | "POSTING" | "POSTED" | "FAILED" | "CANCELLED" | "BLOCKED";

export type AffiliateCommentPlacement = {
  id: string;
  workspace_id: string;
  platform_publication_id: string;
  platform_account_id: string;
  affiliate_product_match_id: string;
  selected_product_id: string;
  growth_assessment_id: string;
  post_job_id: string | null;
  status: AffiliateCommentPlacementStatus;
  idempotency_key: string;
  message_sha256: string;
  comment_message: string;
  cta_text: string;
  disclosure_text: string;
  affiliate_url: string;
  attachment_image_url: string | null;
  template_id: string | null;
  template_version: number | null;
  attach_product_image: boolean;
  external_reel_id: string;
  external_comment_id: string | null;
  external_comment_permalink: string | null;
  created_by: string;
  approved_by: string | null;
  approved_at: string | null;
  posted_at: string | null;
  error_code: string | null;
  error_message: string | null;
  response_summary_json: Record<string, unknown> | null;
  gate_snapshot_json: Record<string, unknown> | null;
  is_current: boolean;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type AffiliateCommentPreviewResponse = {
  reused: boolean;
  placement: AffiliateCommentPlacement;
};

export type AffiliateCommentHistoryResponse = {
  placements: AffiliateCommentPlacement[];
  can_create_another: boolean;
  can_post_now: boolean;
  posted_count_24h: number;
  max_posts_per_24h: number;
  cooldown_hours: number;
  next_allowed_at: string | null;
  blocked_reason: "ACTIVE_PLACEMENT" | "COOLDOWN" | "DAILY_LIMIT" | null;
};

export type AffiliateCommentApproveResponse = {
  placement: AffiliateCommentPlacement;
  job: Job | null;
};

export type AffiliateCommentVerificationStatus = "NOT_CHECKED" | "PENDING" | "VERIFIED" | "NEEDS_ATTENTION" | "CHECK_FAILED";

export type AffiliateCommentVerification = {
  status: AffiliateCommentVerificationStatus;
  checked_at?: string;
  job_id?: string;
  comment?: {
    status?: string;
    message_matches?: boolean;
    attachment_status?: string;
  };
  link?: {
    status?: string;
    status_code?: number | null;
    final_domain?: string;
    redirect_count?: number;
  };
};

export type AffiliateCommentVerificationJobResponse = {
  placement: AffiliateCommentPlacement;
  job: Job;
  reused: boolean;
};
