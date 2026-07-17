import type {
  PlatformAccountHealthStatus,
  PlatformAccountStatus,
  PublishAccountAssignmentStatus,
  PublishDraft,
  PublishDraftStatus,
  PublishTargetPlatform
} from "./publish-draft";

export type AccountHealthSummary = {
  platform_account_id: string;
  display_name: string;
  platform: PublishTargetPlatform;
  account_status: PlatformAccountStatus;
  health_status: PlatformAccountHealthStatus;
  priority: number;
  is_on_hold: boolean;
  cooldown_until: string | null;
  attempts_7d: number;
  succeeded_7d: number;
  failed_7d: number;
  needs_reconciliation_count: number;
  assigned_draft_count: number;
  scheduled_draft_count: number;
  recent_error_code: string | null;
  success_rate_percent: number;
  reasons: string[];
};

export type AccountEligibility = {
  platform_account_id: string;
  display_name: string;
  eligible: boolean;
  health_status: PlatformAccountHealthStatus;
  score: number;
  blocking_reasons: string[];
  warnings: string[];
  recommendation_reasons: string[];
};

export type RoutingRecommendation = {
  publish_draft_id: string;
  matched_rule_ids: string[];
  matched_rule_names: string[];
  recommended_accounts: AccountEligibility[];
  blocked_accounts: AccountEligibility[];
  warnings: string[];
};

export type PublishQueueItem = {
  publish_draft_id: string;
  source_video_id: string;
  title: string | null;
  status: PublishDraftStatus;
  target_platform: PublishTargetPlatform;
  planned_publish_at: string | null;
  assigned_platform_account_id: string | null;
  assignment_status: PublishAccountAssignmentStatus;
  assigned_reason: string | null;
  recommended_platform_account_id: string | null;
  recommended_account_name: string | null;
  recommendation_reasons: string[];
  warnings: string[];
};

export type PublishControlQueue = {
  generated_at: string;
  accounts: AccountHealthSummary[];
  unassigned_drafts: PublishQueueItem[];
  assigned_drafts: PublishQueueItem[];
  scheduled_drafts: PublishQueueItem[];
  needs_attention: PublishQueueItem[];
};

export type RoutingRule = {
  id: string;
  workspace_id: string;
  platform: PublishTargetPlatform;
  rule_name: string;
  status: "ACTIVE" | "PAUSED" | "ARCHIVED";
  priority: number;
  match_json: Record<string, unknown> | null;
  action_json: Record<string, unknown> | null;
  fallback_behavior: string | null;
  metadata_json: Record<string, unknown> | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
};

export type RoutingRuleListResponse = {
  rules: RoutingRule[];
};

export type AssignDraftPayload = {
  platform_account_id: string;
  reason?: string;
  assigned_by?: string;
  force_override?: boolean;
};

export type BulkAssignPayload = AssignDraftPayload & {
  publish_draft_ids: string[];
};

export type AssignmentResult = PublishDraft;

